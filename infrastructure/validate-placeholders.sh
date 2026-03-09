#!/usr/bin/env bash
# Validate required secrets/IDs are set before starting services.
set -euo pipefail

ENV_FILE="${1:-/root/openclaw/.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Env file not found: $ENV_FILE" >&2
    exit 1
fi

required_keys=(
    OPENCLAW_GATEWAY_TOKEN
    DISCORD_BOT_TOKEN
    GOG_KEYRING_PASSWORD
    SENTINEL_TELEGRAM_TOKEN
    SENTINEL_ALLOWED_USERS
    OPENAI_API_KEY
    GEMINI_API_KEY
)

fail=0

validate_key() {
    local key="$1"
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
    if [ -z "$line" ]; then
        echo "[FAIL] Missing key: $key"
        fail=1
        return
    fi
    value="${line#*=}"
    value="${value%%#*}"
    value="$(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' <<<"$value")"
    if [ -z "$value" ]; then
        echo "[FAIL] Empty value for: $key"
        fail=1
    elif [[ "$value" == REPLACE_* ]]; then
        echo "[FAIL] Placeholder value for: $key"
        fail=1
    else
        echo "[PASS] $key"
    fi
}

for key in "${required_keys[@]}"; do
    validate_key "$key"
done

is_truthy() {
    case "${1,,}" in
        1|true|yes|y|on) return 0 ;;
        *) return 1 ;;
    esac
}

openclaw_telegram_enabled="$(grep -E '^OPENCLAW_TELEGRAM_ENABLED=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"
if is_truthy "$openclaw_telegram_enabled"; then
    validate_key OPENCLAW_TELEGRAM_TOKEN
fi

sentinel_discord_enabled="$(grep -E '^SENTINEL_DISCORD_ENABLED=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"
if is_truthy "$sentinel_discord_enabled"; then
    validate_key SENTINEL_DISCORD_BOT_TOKEN
    validate_key SENTINEL_DISCORD_ALLOWED_USERS
fi

if [ "$fail" -ne 0 ]; then
    echo "Validation failed. Fix the env file before starting services." >&2
    exit 1
fi

optional_keys=(
    OPENCLAW_TELEGRAM_TOKEN
    BRAVE_API_KEY
    ANTHROPIC_API_KEY
)

for key in "${optional_keys[@]}"; do
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
    if [ -z "$line" ]; then
        echo "[WARN] Missing optional key: $key"
        continue
    fi
    value="${line#*=}"
    value="${value%%#*}"
    value="$(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' <<<"$value")"
    if [ -z "$value" ] || [[ "$value" == REPLACE_* ]]; then
        echo "[WARN] Optional key unset/placeholder: $key"
    else
        echo "[PASS] $key (optional)"
    fi
done

echo "Validation passed."
