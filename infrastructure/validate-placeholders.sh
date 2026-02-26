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
    GOG_KEYRING_PASSWORD
    OPENCLAW_TELEGRAM_TOKEN
    SENTINEL_TELEGRAM_TOKEN
    SENTINEL_ALLOWED_USERS
    GEMINI_API_KEY
)

fail=0
for key in "${required_keys[@]}"; do
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
    if [ -z "$line" ]; then
        echo "[FAIL] Missing key: $key"
        fail=1
        continue
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
done

if [ "$fail" -ne 0 ]; then
    echo "Validation failed. Fix the env file before starting services." >&2
    exit 1
fi

optional_keys=(
    BRAVE_API_KEY
    ANTHROPIC_API_KEY
)

for key in "${optional_keys[@]}"; do
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
    if [ -z "$line" ]; then
        echo "[WARN] Missing optional key: $key (AI Daily Brief live web grounding will be degraded)"
        continue
    fi
    value="${line#*=}"
    value="${value%%#*}"
    value="$(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' <<<"$value")"
    if [ -z "$value" ] || [[ "$value" == REPLACE_* ]]; then
        echo "[WARN] Optional key unset/placeholder: $key (AI Daily Brief live web grounding will be degraded)"
    else
        echo "[PASS] $key (optional)"
    fi
done

echo "Validation passed."
