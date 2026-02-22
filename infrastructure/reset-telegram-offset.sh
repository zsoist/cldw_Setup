#!/usr/bin/env bash
# Reset Telegram update offset for a channel account and restart gateway.
set -euo pipefail

ACCOUNT_ID="${1:-default}"
ACCOUNT_ID="$(echo "$ACCOUNT_ID" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/_/g')"
OFFSET_FILE="/root/.openclaw/telegram/update-offset-${ACCOUNT_ID}.json"
BACKUP_SUFFIX="$(date -u +%Y%m%dT%H%M%SZ)"

if [ -f "$OFFSET_FILE" ]; then
  cp "$OFFSET_FILE" "${OFFSET_FILE}.bak.${BACKUP_SUFFIX}"
  rm -f "$OFFSET_FILE"
  echo "Removed Telegram update offset: ${OFFSET_FILE}"
  echo "Backup saved: ${OFFSET_FILE}.bak.${BACKUP_SUFFIX}"
else
  echo "No Telegram update offset file found for account '${ACCOUNT_ID}' (${OFFSET_FILE})"
fi

cd /root/openclaw

docker compose restart openclaw-gateway >/dev/null
sleep 10

HEALTH="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' openclaw-openclaw-gateway-1 2>/dev/null || echo unknown)"
echo "Gateway health after restart: ${HEALTH}"

docker compose logs --tail=120 openclaw-gateway | grep -Ei 'telegram|starting provider|error|unauthorized|conflict|getupdates' || true
