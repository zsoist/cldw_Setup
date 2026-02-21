#!/usr/bin/env bash
# Restore OpenClaw from backup
set -euo pipefail

BACKUP_DIR="/root/backups"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup-file>"
    echo ""
    echo "Available backups:"
    ls -lth "$BACKUP_DIR"/openclaw-*.tar.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

validate_archive() {
    local bad=0
    while IFS= read -r entry; do
        case "$entry" in
            root/.openclaw|root/.openclaw/*|opt/sentinel|opt/sentinel/*)
                ;;
            *)
                echo "Refusing restore: unexpected path in archive: $entry"
                bad=1
                ;;
        esac
        case "$entry" in
            /*|../*|*/../*|*..*)
                echo "Refusing restore: unsafe path in archive: $entry"
                bad=1
                ;;
        esac
    done < <(tar tzf "$BACKUP_FILE")
    return "$bad"
}

if ! validate_archive; then
    echo "Restore aborted: backup archive failed safety validation."
    exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo "This will overwrite current OpenClaw config and Sentinel code."
read -p "Continue? (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Stop services before restore
    echo "Stopping services..."
    docker compose -f /root/openclaw/docker-compose.yml down 2>/dev/null || true
    systemctl stop sentinel 2>/dev/null || true

    # Extract backup into root (archive paths are validated above).
    echo "Extracting backup..."
    tar xzf "$BACKUP_FILE" -C /

    # Restart services
    echo "Restarting services..."
    cd /root/openclaw && docker compose up -d
    systemctl start sentinel

    echo "Restore complete. Services restarted."
else
    echo "Restore cancelled."
fi
