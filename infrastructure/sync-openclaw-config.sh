#!/usr/bin/env bash
# Render OpenClaw runtime config from /root/openclaw/.env into mounted config paths.
set -euo pipefail

SOURCE_ENV="${1:-/root/openclaw/.env}"
TEMPLATE_JSON="${2:-/root/openclaw-project/openclaw/openclaw-config.json}"
RUNTIME_JSON="/root/.openclaw/openclaw.json"
RUNTIME_COPY_JSON="/root/.openclaw/openclaw-config.json"
IMAGE_COPY_JSON="/root/openclaw/openclaw-config.json"
TELEGRAM_TOKEN_FILE_HOST="/root/.openclaw/secrets/telegram-default.token"
TELEGRAM_TOKEN_FILE_RUNTIME="/home/node/.openclaw/secrets/telegram-default.token"

if [ ! -f "$SOURCE_ENV" ]; then
    echo "Env file not found: $SOURCE_ENV" >&2
    exit 1
fi

if [ ! -f "$TEMPLATE_JSON" ]; then
    echo "Template config not found: $TEMPLATE_JSON" >&2
    exit 1
fi

extract_key() {
    local key="$1"
    local line value
    line="$(grep -E "^${key}=" "$SOURCE_ENV" | tail -n 1 || true)"
    if [ -z "$line" ]; then
        return 1
    fi
    value="${line#*=}"
    value="${value%%#*}"
    value="$(sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' <<<"$value")"
    if [ -z "$value" ] || [[ "$value" == REPLACE_* ]]; then
        return 1
    fi
    printf "%s" "$value"
}

OPENCLAW_GATEWAY_TOKEN="$(extract_key OPENCLAW_GATEWAY_TOKEN || true)"
OPENCLAW_TELEGRAM_TOKEN="$(extract_key OPENCLAW_TELEGRAM_TOKEN || extract_key TELEGRAM_BOT_TOKEN || true)"
OPENCLAW_TELEGRAM_ALLOW_FROM="$(
    extract_key OPENCLAW_TELEGRAM_ALLOW_FROM ||
        extract_key OPENCLAW_ALLOWED_USERS ||
        extract_key SENTINEL_ALLOWED_USERS ||
        true
)"
OPENCLAW_TELEGRAM_DM_POLICY="$(extract_key OPENCLAW_TELEGRAM_DM_POLICY || true)"
OPENCLAW_GATEWAY_BIND="$(extract_key OPENCLAW_GATEWAY_BIND || true)"
OPENCLAW_GATEWAY_PORT="$(extract_key OPENCLAW_GATEWAY_PORT || true)"

if [ -z "$OPENCLAW_GATEWAY_TOKEN" ] || [ -z "$OPENCLAW_TELEGRAM_TOKEN" ]; then
    echo "Missing required OpenClaw values in $SOURCE_ENV (OPENCLAW_GATEWAY_TOKEN / OPENCLAW_TELEGRAM_TOKEN)." >&2
    exit 1
fi

if [ -z "$OPENCLAW_GATEWAY_BIND" ]; then
    OPENCLAW_GATEWAY_BIND="lan"
fi
if [ -z "$OPENCLAW_GATEWAY_PORT" ]; then
    OPENCLAW_GATEWAY_PORT="18789"
fi
if ! [[ "$OPENCLAW_GATEWAY_PORT" =~ ^[0-9]+$ ]] || [ "$OPENCLAW_GATEWAY_PORT" -lt 1 ] || [ "$OPENCLAW_GATEWAY_PORT" -gt 65535 ]; then
    echo "Invalid OPENCLAW_GATEWAY_PORT: $OPENCLAW_GATEWAY_PORT" >&2
    exit 1
fi

mkdir -p /root/.openclaw
mkdir -p /root/.openclaw/secrets
printf '%s' "$OPENCLAW_TELEGRAM_TOKEN" > "$TELEGRAM_TOKEN_FILE_HOST"
chmod 600 "$TELEGRAM_TOKEN_FILE_HOST"
export OPENCLAW_GATEWAY_TOKEN OPENCLAW_TELEGRAM_TOKEN OPENCLAW_GATEWAY_BIND OPENCLAW_GATEWAY_PORT
export OPENCLAW_TELEGRAM_ALLOW_FROM OPENCLAW_TELEGRAM_DM_POLICY
export TELEGRAM_BOT_TOKEN="$OPENCLAW_TELEGRAM_TOKEN"
export OPENCLAW_TELEGRAM_TOKEN_FILE="$TELEGRAM_TOKEN_FILE_RUNTIME"

python3 - "$TEMPLATE_JSON" "$RUNTIME_JSON" <<'PY'
import json
import os
import re
import sys

template_path, output_path = sys.argv[1], sys.argv[2]

with open(template_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data.setdefault("gateway", {})
data["gateway"]["mode"] = "local"
data["gateway"]["bind"] = os.environ["OPENCLAW_GATEWAY_BIND"]
data["gateway"]["port"] = int(os.environ["OPENCLAW_GATEWAY_PORT"])
data.setdefault("gateway", {}).setdefault("auth", {})
data["gateway"]["auth"]["token"] = os.environ["OPENCLAW_GATEWAY_TOKEN"]

data.setdefault("channels", {}).setdefault("telegram", {})
data["channels"]["telegram"]["enabled"] = True
data["channels"]["telegram"]["botToken"] = os.environ["OPENCLAW_TELEGRAM_TOKEN"]
data["channels"]["telegram"]["tokenFile"] = os.environ["OPENCLAW_TELEGRAM_TOKEN_FILE"]
accounts = data["channels"]["telegram"].setdefault("accounts", {})
default_account = accounts.get("default")
if not isinstance(default_account, dict):
    default_account = {}
default_account["enabled"] = True
default_account["botToken"] = os.environ["OPENCLAW_TELEGRAM_TOKEN"]
default_account["tokenFile"] = os.environ["OPENCLAW_TELEGRAM_TOKEN_FILE"]

allow_from_raw = (os.environ.get("OPENCLAW_TELEGRAM_ALLOW_FROM") or "").strip()
allow_from = []
if allow_from_raw:
    for raw in re.split(r"[\s,]+", allow_from_raw):
        value = raw.strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered.startswith("telegram:") or lowered.startswith("tg:"):
            value = value.split(":", 1)[1].strip()
        if value == "*" or value.isdigit():
            if value not in allow_from:
                allow_from.append(value)

dm_policy_raw = (os.environ.get("OPENCLAW_TELEGRAM_DM_POLICY") or "").strip().lower()
if dm_policy_raw in {"pairing", "allowlist", "open", "disabled"}:
    dm_policy = dm_policy_raw
elif allow_from:
    dm_policy = "allowlist"
else:
    dm_policy = "pairing"

data["channels"]["telegram"]["dmPolicy"] = dm_policy
default_account["dmPolicy"] = dm_policy
if allow_from:
    data["channels"]["telegram"]["allowFrom"] = allow_from
    default_account["allowFrom"] = allow_from
else:
    data["channels"]["telegram"].pop("allowFrom", None)
    default_account.pop("allowFrom", None)

accounts["default"] = default_account
data["channels"]["telegram"].setdefault("commands", {})
data["channels"]["telegram"]["commands"]["native"] = True
data["channels"]["telegram"]["commands"]["nativeSkills"] = True

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

cp "$RUNTIME_JSON" "$RUNTIME_COPY_JSON"
cp "$RUNTIME_JSON" "$IMAGE_COPY_JSON"

chmod 600 "$RUNTIME_JSON" "$RUNTIME_COPY_JSON" "$IMAGE_COPY_JSON" "$TELEGRAM_TOKEN_FILE_HOST"

resolve_owner() {
    local owner=""
    local uid=""
    local gid=""
    stat_owner() {
        local path="$1"
        stat -c '%u:%g' "$path" 2>/dev/null || stat -f '%u:%g' "$path" 2>/dev/null || true
    }

    if [[ "${OPENCLAW_CONFIG_UID:-}" =~ ^[0-9]+$ ]] && [[ "${OPENCLAW_CONFIG_GID:-}" =~ ^[0-9]+$ ]]; then
        owner="${OPENCLAW_CONFIG_UID}:${OPENCLAW_CONFIG_GID}"
    elif [ -n "${OPENCLAW_RUNTIME_OWNER:-}" ]; then
        owner="${OPENCLAW_RUNTIME_OWNER}"
    elif command -v docker >/dev/null 2>&1 && [ -f /root/openclaw/docker-compose.yml ]; then
        uid="$(docker compose -f /root/openclaw/docker-compose.yml run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -u openclaw' 2>/dev/null | tr -d '\r' | tail -n 1 || true)"
        gid="$(docker compose -f /root/openclaw/docker-compose.yml run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -g openclaw' 2>/dev/null | tr -d '\r' | tail -n 1 || true)"
        if [[ "$uid" =~ ^[0-9]+$ ]] && [[ "$gid" =~ ^[0-9]+$ ]]; then
            owner="${uid}:${gid}"
        fi
    fi
    if [ -z "$owner" ] && [ -d /root/.openclaw ]; then
        owner="$(stat_owner /root/.openclaw)"
    fi

    if [ -n "$owner" ]; then
        chown "$owner" "$RUNTIME_JSON" "$RUNTIME_COPY_JSON" "$IMAGE_COPY_JSON" "$TELEGRAM_TOKEN_FILE_HOST"
    fi
}

resolve_owner

echo "Wrote OpenClaw config: $RUNTIME_JSON"
