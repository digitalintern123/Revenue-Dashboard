# Encalm Analytics - daily database backup (SQLite)
#
# Schedule with Windows Task Scheduler, daily at 02:00 (see docs/SERVER_RUNBOOK.md):
#   schtasks /create /tn EncalmBackup /sc daily /st 02:00 /ru SYSTEM /f /tr
#     "powershell -NoProfile -ExecutionPolicy Bypass -File C:\encalm\backup_db.ps1"
#
# 1. Copies C:\encalm\data\revenue_analytics.db to C:\encalm\backups (safe
#    while the app is running) and checks the copy (integrity + row counts).
# 2. Copies it OFF this server to the folder named on the first line of
#    C:\encalm\backup_offsite.txt (not in git), e.g. a network share
#    \\nas\encalm-backups or a OneDrive/SharePoint-synced folder.
# 3. Keeps 30 local and 90 off-server copies; alerts (notify.ps1) on failure.
#
# No passwords are needed: the database is a local SQLite file.

$AppDir    = "C:\encalm"
$Python    = "C:\Users\encalmit\AppData\Local\Python\bin\python.exe"
$Database  = Join-Path $AppDir "data\revenue_analytics.db"
$BackupDir = Join-Path $AppDir "backups"
$LogFile   = Join-Path $AppDir "logs\backup.log"

. (Join-Path $PSScriptRoot "notify.ps1")

function Write-Log($msg) {
    $dir = Split-Path $LogFile
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    Add-Content -Path $LogFile -Value ("{0} [BACKUP] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

$Offsite = $null
$cfg = Join-Path $AppDir "backup_offsite.txt"
if (Test-Path $cfg) { $Offsite = (Get-Content $cfg -TotalCount 1).Trim() }

$argsList = @((Join-Path $AppDir "scripts\backup_sqlite.py"),
              "--db", $Database, "--dest", $BackupDir, "--keep", "30")
if ($Offsite) { $argsList += @("--offsite", $Offsite, "--keep-offsite", "90") }

$out = & $Python @argsList 2>&1 | Out-String
$code = $LASTEXITCODE
Write-Log ($out.Trim())

if ($code -ne 0) {
    Send-EncalmAlert -Title "Database backup FAILED" -Text $out.Trim() -Key "backup-failed"
    exit 1
}
if (-not $Offsite) {
    Write-Log "WARNING: no off-server copy (C:\encalm\backup_offsite.txt not set)"
    Send-EncalmAlert -Title "Backup has no off-server copy" `
        -Text "Set the off-server backup folder in C:\encalm\backup_offsite.txt" -Key "backup-no-offsite"
}
exit 0
