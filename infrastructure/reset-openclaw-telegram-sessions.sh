#!/usr/bin/env bash
# Reset OpenClaw runtime sessions to clear stale conversational context/noisy narration drift.
set -euo pipefail

SESS_DIR="${SESS_DIR:-/root/.openclaw/agents/main/sessions}"
SESS_INDEX="${SESS_INDEX:-${SESS_DIR}/sessions.json}"
CONTAINER_NAME="${CONTAINER_NAME:-openclaw-openclaw-gateway-1}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-/root/.openclaw/agents/main/sessions-reset-${TS}}"

if [ ! -d "$SESS_DIR" ]; then
  echo "Session directory not found: $SESS_DIR" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

if [ -f "$SESS_INDEX" ]; then
  cp "$SESS_INDEX" "${BACKUP_DIR}/sessions.json.bak"
fi

moved=0
for f in "$SESS_DIR"/*.jsonl; do
  [ -f "$f" ] || continue
  base="$(basename "$f")"
  case "$base" in
    probe-*)
      # Keep probe sessions for diagnostics.
      continue
      ;;
  esac
  mv "$f" "$BACKUP_DIR/"
  moved=$((moved + 1))
done

printf '{}\n' > "$SESS_INDEX"
chmod 600 "$SESS_INDEX"

echo "Backed up sessions to: $BACKUP_DIR"
echo "Moved non-probe session logs: $moved"
echo "Reset session index: $SESS_INDEX"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker restart "$CONTAINER_NAME" >/dev/null
  echo "Restarted container: $CONTAINER_NAME"
else
  echo "Container not found: $CONTAINER_NAME (skipped restart)"
fi
