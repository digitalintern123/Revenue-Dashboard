# Encalm Analytics — Daily Database Backup Script (v2)
# Schedule via Windows Task Scheduler: daily at 2:00 AM
# Keeps last 30 days of backups.

$PgBin     = "C:\Program Files\PostgreSQL\17\bin"
$BackupDir = "C:\encalm\backups"
$DBName    = "encalm_analytics"
$DBUser    = "encalm_user"
$LogFile   = "C:\encalm\logs\backup.log"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$BackupFile = "$BackupDir\encalm_${Timestamp}.sql"

# Ensure dirs exist
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path $LogFile) -Force | Out-Null

# Run pg_dump
$env:PGPASSWORD = "Encalm@2026"
& "$PgBin\pg_dump.exe" -U $DBUser -d $DBName -f $BackupFile

if ($LASTEXITCODE -eq 0) {
    $size = (Get-Item $BackupFile).Length / 1KB
    Add-Content -Path $LogFile -Value "$(Get-Date) [BACKUP] SUCCESS: $BackupFile ($([math]::Round($size,1)) KB)"
} else {
    Add-Content -Path $LogFile -Value "$(Get-Date) [BACKUP] FAILED: pg_dump exit code $LASTEXITCODE"
}

# Delete backups older than 30 days
Get-ChildItem -Path $BackupDir -Filter "encalm_*.sql" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force

Add-Content -Path $LogFile -Value "$(Get-Date) [BACKUP] Cleanup complete. Current backups: $(Get-ChildItem $BackupDir -Filter '*.sql').Count"
