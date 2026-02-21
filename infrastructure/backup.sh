#!/usr/bin/env bash
# Automated backup of OpenClaw state
set -euo pipefail

BACKUP_DIR="/root/backups"
TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
BACKUP_FILE="$BACKUP_DIR/openclaw-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

TMP_FILE_LIST="$(mktemp)"
cleanup() {
    rm -f "$TMP_FILE_LIST"
}
trap cleanup EXIT

# Build a strict allowlist of files to back up.
find /root/.openclaw -xdev -type f \
    ! -name '.env' \
    ! -name '*.env' \
    ! -name '*.pem' \
    ! -name '*.key' \
    ! -name '*.crt' \
    ! -path '*/credentials/*' \
    -print >"$TMP_FILE_LIST"

find /opt/sentinel -maxdepth 1 -type f \
    \( -name '*.py' -o -name 'requirements.txt' -o -name 'sentinel.service' \) \
    -print >>"$TMP_FILE_LIST"

if [ ! -s "$TMP_FILE_LIST" ]; then
    echo "Backup aborted: no files matched allowlist." >&2
    exit 1
fi

tar czf "$BACKUP_FILE" --files-from "$TMP_FILE_LIST"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/openclaw-*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true

SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
echo "Backup created: $BACKUP_FILE ($SIZE)"
