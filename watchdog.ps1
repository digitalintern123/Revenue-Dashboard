# Encalm Analytics — Watchdog Script (v2)
# Run via Windows Task Scheduler every 3 minutes.
# Automatically restarts the Streamlit app if it stops responding on port 8501.

$Port = 8501
$TaskName = "EncalmAnalytics"
$LogFile = "C:\encalm\logs\watchdog.log"

# Ensure log directory exists
$LogDir = Split-Path $LogFile
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$listening = netstat -an | Select-String "0.0.0.0:$Port.*LISTENING"

if (-not $listening) {
    Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] App not listening on $Port — restarting task '$TaskName'"
    schtasks /run /tn $TaskName
    Start-Sleep -Seconds 20
    $check = netstat -an | Select-String "0.0.0.0:$Port.*LISTENING"
    if ($check) {
        Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] App restarted successfully"
    } else {
        Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] WARNING: App did not come back up — manual intervention required"
    }
} else {
    Add-Content -Path $LogFile -Value "$timestamp [WATCHDOG] App healthy on port $Port"
}
