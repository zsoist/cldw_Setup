#!/usr/bin/env bash
# Configure AI Daily Brief output channel in state file.
set -euo pipefail

CHANNEL_INPUT="${1:-}"
STATE_FILE="${2:-/root/.openclaw/workspace/logs/ai-brief-state.json}"

usage() {
  cat <<'EOF'
Usage:
  set-aibrief-output-channel.sh <channel> [state_file]

Examples:
  set-aibrief-output-channel.sh @dandailybriefAI
  set-aibrief-output-channel.sh dandailybriefAI
  set-aibrief-output-channel.sh https://t.me/dandailybriefAI
  set-aibrief-output-channel.sh -1001234567890

Notes:
  - Username targets are normalized to @username.
  - Numeric chat IDs are preserved as-is.
EOF
}

if [ -z "$CHANNEL_INPUT" ]; then
  usage
  exit 1
fi

normalize_channel() {
  local raw="$1"
  raw="$(printf '%s' "$raw" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

  if [[ "$raw" =~ ^https?://t\.me/([A-Za-z0-9_]{5,})/?$ ]]; then
    printf "@%s" "${BASH_REMATCH[1]}"
    return 0
  fi

  if [[ "$raw" =~ ^@?[A-Za-z0-9_]{5,}$ ]]; then
    raw="${raw#@}"
    printf "@%s" "$raw"
    return 0
  fi

  if [[ "$raw" =~ ^-100[0-9]{6,}$ ]] || [[ "$raw" =~ ^[0-9]{6,}$ ]]; then
    printf "%s" "$raw"
    return 0
  fi

  return 1
}

if ! NORMALIZED_CHANNEL="$(normalize_channel "$CHANNEL_INPUT")"; then
  echo "Invalid channel format: $CHANNEL_INPUT" >&2
  usage >&2
  exit 1
fi

if [ ! -f "$STATE_FILE" ]; then
  echo "State file not found: $STATE_FILE" >&2
  exit 1
fi

cp "$STATE_FILE" "${STATE_FILE}.bak.$(date -u +%Y%m%dT%H%M%SZ)"

python3 - "$STATE_FILE" "$NORMALIZED_CHANNEL" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
channel = sys.argv[2]

data = json.loads(path.read_text(encoding="utf-8"))
config = data.setdefault("config", {})
config["output_channel"] = channel
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(channel)
PY

chmod 600 "$STATE_FILE"
echo "Configured ai_daily_brief output_channel=${NORMALIZED_CHANNEL} in ${STATE_FILE}"
