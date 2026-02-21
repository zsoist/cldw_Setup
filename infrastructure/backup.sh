#!/usr/bin/env bash
# Automated backup of OpenClaw state
set -euo pipefail

BACKUP_DIR="/root/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/openclaw-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

tar czf "$BACKUP_FILE" \
    --exclude='*.env' \
    --exclude='*.pem' \
    --exclude='*.key' \
    /root/.openclaw/ \
    /opt/sentinel/*.py \
    /opt/sentinel/requirements.txt \
    2>/dev/null

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/openclaw-*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Backup created: $BACKUP_FILE ($SIZE)"
