#!/usr/bin/env bash
# ocdash — Open the OpenClaw gateway dashboard from your Mac.
#
# Usage:
#   ocdash          # Opens dashboard in default browser
#   ocdash --url    # Prints the URL without opening
#
# Prerequisites:
#   1. SSH config has a "Host openclaw" entry (see ssh-config-snippet)
#   2. SSH key auth configured (no password prompts)
#
# Install as a shell function (add to ~/.zshrc or ~/.bash_profile):
#
#   ocdash() { bash /path/to/openclaw-project/infrastructure/ocdash.sh "$@"; }
#
# Or copy the function below directly into your shell profile.

set -euo pipefail

SSH_HOST="${OCDASH_SSH_HOST:-openclaw}"
LOCAL_PORT="${OCDASH_LOCAL_PORT:-28789}"
REMOTE_PORT="${OCDASH_REMOTE_PORT:-18789}"

# ---------- helpers ----------
die()  { echo "❌ $*" >&2; exit 1; }
info() { echo "→ $*"; }

cleanup() {
    if [[ -n "${TUNNEL_PID:-}" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        kill "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
        info "SSH tunnel closed."
    fi
}
trap cleanup EXIT

# ---------- check port availability ----------
if lsof -iTCP:"$LOCAL_PORT" -sTCP:LISTEN -t &>/dev/null; then
    info "Port $LOCAL_PORT already in use — reusing existing tunnel."
    TUNNEL_PID=""
else
    info "Opening SSH tunnel ($LOCAL_PORT → $REMOTE_PORT)..."
    ssh -f -N -L "$LOCAL_PORT:127.0.0.1:$REMOTE_PORT" "$SSH_HOST" \
        || die "SSH tunnel failed. Check your SSH config for Host '$SSH_HOST'."
    TUNNEL_PID=$(lsof -iTCP:"$LOCAL_PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)
    [[ -n "$TUNNEL_PID" ]] || die "Tunnel started but PID not found."
    sleep 1
fi

# ---------- get tokenized dashboard URL ----------
info "Fetching dashboard URL..."
RAW_URL=$(ssh "$SSH_HOST" \
    'docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs dashboard --no-open 2>/dev/null' \
    | sed -n 's/^Dashboard URL: //p' | head -1) \
    || die "Failed to get dashboard URL. Is the OpenClaw container running?"

[[ -n "$RAW_URL" ]] || die "Dashboard URL empty. Check: docker ps on VPS."

# Rewrite URL for local tunnel port
URL="${RAW_URL/127.0.0.1:$REMOTE_PORT/127.0.0.1:$LOCAL_PORT}"

# ---------- output ----------
if [[ "${1:-}" == "--url" ]]; then
    echo "$URL"
else
    info "Opening: $URL"
    if command -v open &>/dev/null; then
        open "$URL"                     # macOS
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$URL"                 # Linux
    else
        echo "$URL"
        info "(No browser opener found — copy the URL above)"
    fi
    # Keep tunnel alive if we opened it
    if [[ -n "${TUNNEL_PID:-}" ]]; then
        info "Tunnel running (PID $TUNNEL_PID). Press Ctrl+C to close."
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi
fi
