#!/usr/bin/env bash
# Nightly PostgreSQL backup: dump locally, keep 14 days, copy off the server.
#
# Install (as root):
#   cp deploy/backup_postgres.sh /usr/local/bin/encalm-backup && chmod 700 /usr/local/bin/encalm-backup
#   crontab -e   →   15 2 * * *  /usr/local/bin/encalm-backup >> /var/log/encalm-backup.log 2>&1
#
# Off-server copy — set ONE of these (in /etc/encalm-backup.conf or below):
#   RCLONE_REMOTE="gdrive:encalm-backups"      # any rclone remote: Google Drive, S3, Backblaze B2…
#   RSYNC_TARGET="backup@other-server:/backups/encalm/"
# Restore:  pg_restore --clean --if-exists -d encalm /var/backups/encalm/encalm_YYYY-MM-DD_HHMM.dump
set -euo pipefail

[ -f /etc/encalm-backup.conf ] && . /etc/encalm-backup.conf
DB_NAME="${DB_NAME:-encalm}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/encalm}"
KEEP_DAYS="${KEEP_DAYS:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
RSYNC_TARGET="${RSYNC_TARGET:-}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
FILE="$BACKUP_DIR/${DB_NAME}_$(date +%F_%H%M).dump"

# Custom format: compressed, restorable table by table with pg_restore
sudo -u postgres pg_dump -Fc "$DB_NAME" > "$FILE"
# Fail loudly on an empty/broken dump
pg_restore --list "$FILE" > /dev/null
echo "$(date '+%F %T') dump OK: $FILE ($(du -h "$FILE" | cut -f1))"

find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime +"$KEEP_DAYS" -delete

need() { command -v "$1" >/dev/null || { echo "ERROR: $1 is not installed (apt install $1)" >&2; exit 1; }; }

if [ -n "$RCLONE_REMOTE" ]; then
    need rclone
    rclone copy "$FILE" "$RCLONE_REMOTE" && echo "copied to $RCLONE_REMOTE"
    rclone delete --min-age "${KEEP_DAYS}d" "$RCLONE_REMOTE" || true
elif [ -n "$RSYNC_TARGET" ]; then
    need rsync
    rsync -a "$FILE" "$RSYNC_TARGET" && echo "copied to $RSYNC_TARGET"
else
    echo "WARNING: no off-server target set (RCLONE_REMOTE or RSYNC_TARGET) — backup is only on this VPS." >&2
fi
