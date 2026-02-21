#!/usr/bin/env bash
# Restore OpenClaw from backup
set -euo pipefail

BACKUP_DIR="/root/backups"
TMP_RESTORE="$(mktemp -d /tmp/openclaw-restore.XXXXXX)"
cleanup() {
    rm -rf "$TMP_RESTORE"
}
trap cleanup EXIT

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
    python3 - "$BACKUP_FILE" <<'PY'
import posixpath
import sys
import tarfile

archive = sys.argv[1]

def allowed_path(name: str) -> bool:
    return (
        name == "root/.openclaw"
        or name.startswith("root/.openclaw/")
        or name == "opt/sentinel"
        or name.startswith("opt/sentinel/")
    )

with tarfile.open(archive, "r:gz") as tf:
    for member in tf.getmembers():
        raw_name = member.name.lstrip("./")
        normalized = posixpath.normpath(raw_name)
        if normalized in ("", ".", ".."):
            print(f"Refusing restore: unsafe archive path: {member.name}")
            sys.exit(1)
        if normalized.startswith("../") or "/../" in f"/{normalized}/":
            print(f"Refusing restore: traversal path in archive: {member.name}")
            sys.exit(1)
        if not allowed_path(normalized):
            print(f"Refusing restore: unexpected path in archive: {member.name}")
            sys.exit(1)
        if not (member.isfile() or member.isdir()):
            print(f"Refusing restore: unsupported archive entry type for {member.name}")
            sys.exit(1)
PY
}

if ! validate_archive; then
    echo "Restore aborted: backup archive failed safety validation."
    exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo "This will overwrite current OpenClaw config and Sentinel code."
read -r -p "Continue? (y/N) " -n 1 REPLY
echo

if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

echo "Stopping services..."
docker compose -f /root/openclaw/docker-compose.yml down 2>/dev/null || true
systemctl stop sentinel 2>/dev/null || true

echo "Extracting backup to temporary directory..."
tar xzf "$BACKUP_FILE" -C "$TMP_RESTORE" --no-same-owner --no-same-permissions

echo "Applying restored files..."
if [ -d "$TMP_RESTORE/root/.openclaw" ]; then
    mkdir -p /root/.openclaw
    cp -a "$TMP_RESTORE/root/.openclaw/." /root/.openclaw/
fi

if [ -d "$TMP_RESTORE/opt/sentinel" ]; then
    mkdir -p /opt/sentinel
    find "$TMP_RESTORE/opt/sentinel" -maxdepth 1 -type f \( -name '*.py' -o -name 'requirements.txt' -o -name 'sentinel.service' \) -print0 \
        | while IFS= read -r -d '' file; do
            cp -a "$file" /opt/sentinel/
        done
fi

if id sentinel >/dev/null 2>&1; then
    chown -R sentinel:sentinel /opt/sentinel
fi

echo "Restarting services..."
cd /root/openclaw && docker compose up -d
systemctl daemon-reload
systemctl start sentinel

echo "Restore complete. Services restarted."
