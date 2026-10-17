# Encalm Analytics - Watchdog Script (v2)
# Run via Windows Task Scheduler every 3 minutes.
# Automatically restarts the Streamlit app if it stops responding on port 8501,
# and alerts (notify.ps1) when it had to restart it, when it cannot, and when
# the newest database backup is more than 26 hours old.

$Port = 8501
$TaskName = "EncalmAnalytics"
$LogFile = "C:\encalm\logs\watchdog.log"
$BackupDir = "C:\encalm\backups"
$BackupMaxAgeHours = 26

. (Join-Path $PSScriptRoot "notify.ps1")

# Apply new commits that Plesk Git pulled from GitHub (see deploy_sync.ps1)
$DeploySync = Join-Path $PSScriptRoot "deploy_sync.ps1"
if (Test-Path $DeploySync) { & $DeploySync }

# Ensure log directory exists
$LogDir = Split-Path $LogFile
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$listening = netstat -an | Select-String "0.0.0.0:$Port.*LISTENING"

if (-not $listening) {
    Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] App not listening on $Port - restarting task '$TaskName'"
    schtasks /run /tn $TaskName
    Start-Sleep -Seconds 20
    $check = netstat -an | Select-String "0.0.0.0:$Port.*LISTENING"
    if ($check) {
        Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] App restarted successfully"
        Send-EncalmAlert -Title "App was down - restarted" `
            -Text "The app stopped listening on port $Port and was restarted by the watchdog." -Key "app-restarted"
    } else {
        Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] WARNING: App did not come back up - manual intervention required"
        Send-EncalmAlert -Title "App is DOWN" `
            -Text "The watchdog could not restart the app (port $Port). Check C:\encalm\logs on the server." -Key "app-down"
    }
} else {
    Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] App healthy on port $Port"
}

# Backups: alert if the newest backup is too old (backup task not running).
$newest = Get-ChildItem -Path $BackupDir -Filter "revenue_analytics_*.db" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $newest) {
    Send-EncalmAlert -Title "No database backups found" `
        -Text "Nothing in $BackupDir. Is the EncalmBackup scheduled task set up?" -Key "backup-stale"
} elseif (((Get-Date) - $newest.LastWriteTime).TotalHours -gt $BackupMaxAgeHours) {
    Send-EncalmAlert -Title "Database backup is out of date" `
        -Text ("Newest backup {0} is from {1}." -f $newest.Name, $newest.LastWriteTime) -Key "backup-stale"
}
