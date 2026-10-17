# Encalm Analytics - Plesk Git deploy sync (Windows)
#
# Plesk's Git extension keeps a copy of the GitHub repository on the server
# (updated on "Pull now" or automatically by the GitHub webhook). This script
# brings new commits from that copy into the app folder (C:\encalm), installs
# any new Python packages, and restarts the app.
#
# It is called by watchdog.ps1 every 3 minutes, so a push to GitHub is live
# within a few minutes. It does nothing when there is nothing new, and it
# never touches data\, .streamlit\secrets.toml, logs\, backups\ or exports\
# (they are not in git).
#
# Optional: create C:\encalm\deploy_source.txt containing the full path of
# the Plesk repository (e.g. C:\Inetpub\vhosts\example.com\git\Revenue-Dashboard.git)
# if it is not found automatically.

$AppDir   = "C:\encalm"
$Python   = "C:\Users\encalmit\AppData\Local\Python\bin\python.exe"
$TaskName = "EncalmAnalytics"
$Port     = 8501
$LogFile  = Join-Path $AppDir "logs\deploy.log"

. (Join-Path $PSScriptRoot "notify.ps1")

function Write-Log($msg) {
    $dir = Split-Path $LogFile
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    Add-Content -Path $LogFile -Value ("{0} [DEPLOY] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

function Invoke-Git {
    # safe.directory=*: the Plesk repository belongs to the site's user, not to us
    $out = & git -c safe.directory=* -C $AppDir @args 2>&1
    return @{ Code = $LASTEXITCODE; Out = ($out | Out-String).Trim() }
}

# -- Where is the Plesk copy of the repository? ------------------------------
$Source = $null
$cfg = Join-Path $AppDir "deploy_source.txt"
if (Test-Path $cfg) { $Source = (Get-Content $cfg -TotalCount 1).Trim() }
if (-not $Source) {
    $found = Get-ChildItem "C:\Inetpub\vhosts\*\git\*.git" -Directory -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -like "*Revenue*" } | Select-Object -First 1
    if ($found) { $Source = $found.FullName }
}
# Page files moved from pages\ to views\: a leftover pages\ folder (only
# __pycache__ after the move) must go, or Streamlit serves pages unstyled.
$oldPages = Join-Path $AppDir "pages"
if ((Test-Path $oldPages) -and -not (Get-ChildItem $oldPages -Filter *.py -ErrorAction SilentlyContinue)) {
    Remove-Item $oldPages -Recurse -Force -ErrorAction SilentlyContinue
    Write-Log "removed leftover pages folder"
}

if (-not $Source -or -not (Test-Path $Source)) { exit 0 }   # Plesk Git not set up yet

$branch = (Invoke-Git rev-parse --abbrev-ref HEAD).Out
$before = (Invoke-Git rev-parse HEAD).Out

$fetch = Invoke-Git fetch --quiet $Source $branch
if ($fetch.Code -ne 0) {
    Write-Log "fetch from $Source ($branch) failed: $($fetch.Out)"
    Send-EncalmAlert -Title "Update check failed" -Text "git fetch ($branch): $($fetch.Out)" -Key "deploy-fetch"
    exit 1
}
$new = (Invoke-Git rev-parse FETCH_HEAD).Out
if ($new -eq $before) { exit 0 }                             # nothing new

$changed = (Invoke-Git diff --name-only $before $new).Out
$merge = Invoke-Git merge --ff-only FETCH_HEAD
if ($merge.Code -ne 0) {
    Write-Log "update to $new not applied (local changes in the way?): $($merge.Out)"
    Send-EncalmAlert -Title "Update NOT applied" `
        -Text "New commits on $branch could not be applied: $($merge.Out)" -Key "deploy-merge"
    exit 1
}
Write-Log "updated $($before.Substring(0,7)) -> $($new.Substring(0,7)) on $branch"

if ($changed -match "requirements\.txt") {
    $pip = & $Python -m pip install -q -r (Join-Path $AppDir "requirements.txt") 2>&1 | Out-String
    Write-Log "requirements.txt changed - pip install done. $($pip.Trim())"
}

# -- Restart the app ---------------------------------------------------------
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 20
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Log "app restarted on port $Port"
} else {
    Write-Log "WARNING: app not listening on port $Port after restart"
    Send-EncalmAlert -Title "App did not start after update" `
        -Text "Updated to $($new.Substring(0,7)) on $branch but nothing listens on port $Port." -Key "deploy-restart"
}
