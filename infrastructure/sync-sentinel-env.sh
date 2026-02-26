#!/usr/bin/env bash
# Sync Sentinel environment variables from OpenClaw .env into /etc/sentinel/sentinel.env
set -euo pipefail

SOURCE_ENV="/root/openclaw/.env"
TARGET_ENV="/etc/sentinel/sentinel.env"
TMP_ENV="$(mktemp)"

cleanup() {
    rm -f "$TMP_ENV"
}
trap cleanup EXIT

if [ ! -f "$SOURCE_ENV" ]; then
    echo "Source env file not found: $SOURCE_ENV" >&2
    exit 1
fi

if ! getent group sentinel >/dev/null 2>&1; then
    echo "Group 'sentinel' does not exist. Run deploy.sh first." >&2
    exit 1
fi

extract_key() {
    local key="$1"
    local line
    line="$(grep -E "^${key}=" "$SOURCE_ENV" | tail -n 1 || true)"
    if [ -z "$line" ]; then
        return 0
    fi
    local value="${line#*=}"
    value="${value%%#*}"
    value="$(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' <<<"$value")"
    printf "%s=%s\n" "$key" "$value" >>"$TMP_ENV"
}

# Only include Sentinel-required keys.
for key in \
    SENTINEL_TELEGRAM_TOKEN \
    SENTINEL_ALLOWED_USERS \
    SENTINEL_PROVIDER \
    SENTINEL_MODEL \
    SENTINEL_MAX_TOKENS \
    SENTINEL_USD_TO_COP_RATE \
    ANTHROPIC_API_KEY \
    GEMINI_API_KEY \
    SENTINEL_RATE_LIMIT_MAX_REQUESTS \
    SENTINEL_RATE_LIMIT_WINDOW_SECONDS \
    SENTINEL_CONVERSATION_TTL_SECONDS \
    SENTINEL_MAX_TOOL_ITERATIONS \
    SENTINEL_COST_TRACKING_ENABLED \
    SENTINEL_API_USAGE_LOG_FILE \
    SENTINEL_API_COST_SUMMARY_FILE \
    SENTINEL_COST_RETENTION_DAYS; do
    extract_key "$key"
done

install -o root -g sentinel -m 640 "$TMP_ENV" "$TARGET_ENV"
echo "Wrote $TARGET_ENV"
