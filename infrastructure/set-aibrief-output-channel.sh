#!/usr/bin/env bash
# Configure AI Daily Brief output channel in state file.
set -euo pipefail

CHANNEL_INPUT="${1:-}"
STATE_FILE="${2:-/root/.openclaw/workspace/logs/ai-brief-state.json}"
ENV_FILE="${3:-/root/openclaw/.env}"

usage() {
  cat <<'EOF'
Usage:
  set-aibrief-output-channel.sh <channel> [state_file] [env_file]

Examples:
  set-aibrief-output-channel.sh @dandailybriefAI
  set-aibrief-output-channel.sh dandailybriefAI
  set-aibrief-output-channel.sh https://t.me/dandailybriefAI
  set-aibrief-output-channel.sh -1001234567890

Notes:
  - Username targets are normalized to @username.
  - Numeric chat IDs are preserved as-is.
  - When env_file exists and channel is numeric, script also updates
    OPENCLAW_TELEGRAM_INTERACTIVE_CHATS to include that chat ID.
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

if [ -f "$ENV_FILE" ] && ([[ "$NORMALIZED_CHANNEL" =~ ^-100[0-9]{6,}$ ]] || [[ "$NORMALIZED_CHANNEL" =~ ^[0-9]{6,}$ ]]); then
  UPDATED_INTERACTIVE="$(
    python3 - "$ENV_FILE" "$NORMALIZED_CHANNEL" <<'PY'
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
new_chat = sys.argv[2].strip()
lines = env_path.read_text(encoding="utf-8").splitlines()

existing = ""
out_lines = []
for line in lines:
    if line.startswith("OPENCLAW_TELEGRAM_INTERACTIVE_CHATS="):
        existing = line.split("=", 1)[1].strip()
        continue
    out_lines.append(line)

items = []
seen = set()
if existing:
    for raw in re.split(r"[\s,]+", existing):
        value = raw.strip()
        if not value:
            continue
        if value not in seen:
            items.append(value)
            seen.add(value)
if new_chat and new_chat not in seen:
    items.append(new_chat)

merged = ",".join(items)
out_lines.append(f"OPENCLAW_TELEGRAM_INTERACTIVE_CHATS={merged}")
env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
print(merged)
PY
  )"
  echo "Updated OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=${UPDATED_INTERACTIVE} in ${ENV_FILE}"
fi
