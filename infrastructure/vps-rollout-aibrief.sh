#!/usr/bin/env bash
# Update cldw_Setup on VPS, sync AI Daily Brief assets, restart services, and validate health.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/root/openclaw-project}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/root/openclaw}"
OPENCLAW_CFG="${OPENCLAW_CFG:-/root/.openclaw}"
BRANCH="${BRANCH:-main}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-18}"
WAIT_SECONDS="${WAIT_SECONDS:-10}"

log() {
  printf '[aibrief-rollout] %s\n' "$*"
}

require_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
}

log "Syncing repository to origin/${BRANCH}"
cd "$PROJECT_DIR"
git fetch origin
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"
CURRENT_REF="$(git rev-parse --short HEAD)"
log "Using project ref: ${CURRENT_REF}"

log "Syncing AI Daily Brief config and skill assets"
mkdir -p \
  "$OPENCLAW_CFG/workspace" \
  "$OPENCLAW_CFG/workspace/logs"

# Keep runtime compose/config templates in sync during config-only rollouts.
cp "$PROJECT_DIR/infrastructure/docker-compose.yml" "$OPENCLAW_DIR/docker-compose.yml"
cp "$PROJECT_DIR/openclaw/openclaw-config.json" "$OPENCLAW_DIR/openclaw-config.json"

# OpenClaw loads AGENTS/SOUL/HEARTBEAT/etc from the agent workspace root.
# Keep root copies for legacy tooling, but always sync workspace bootstrap files.
for bootstrap in AGENTS.md SOUL.md TOOLS.md IDENTITY.md USER.md HEARTBEAT.md BOOTSTRAP.md MEMORY.md; do
  cp "$PROJECT_DIR/openclaw/config/$bootstrap" "$OPENCLAW_CFG/workspace/$bootstrap"
  cp "$PROJECT_DIR/openclaw/config/$bootstrap" "$OPENCLAW_CFG/$bootstrap"
done
cp "$PROJECT_DIR/openclaw/config/CRON.md" "$OPENCLAW_CFG/workspace/CRON.md"
cp "$PROJECT_DIR/openclaw/config/CRON.md" "$OPENCLAW_CFG/CRON.md"
# Sync all skills recursively to keep alias commands current.
if [ -d "$PROJECT_DIR/openclaw/skills" ]; then
  while IFS= read -r -d '' skill_file; do
    rel_path="${skill_file#$PROJECT_DIR/openclaw/skills/}"
    mkdir -p "$(dirname "$OPENCLAW_CFG/skills/$rel_path")"
    cp "$skill_file" "$OPENCLAW_CFG/skills/$rel_path"
  done < <(find "$PROJECT_DIR/openclaw/skills" -type f -print0)
fi

# Remove deprecated alias skill folders to avoid confusing/duplicate command surfaces.
for deprecated in \
  aibrief \
  aibrief_morning \
  aibrief_evening \
  aibrief_top5 \
  aibrief_builder \
  aibrief_watchlist \
  aibrief_status; do
  rm -rf "$OPENCLAW_CFG/skills/$deprecated"
done
bash "$PROJECT_DIR/infrastructure/merge-ai-brief-state.sh" \
  "$PROJECT_DIR/openclaw/workspace/logs/ai-brief-state.json" \
  "$OPENCLAW_CFG/workspace/logs/ai-brief-state.json"

require_file "$OPENCLAW_CFG/openclaw.json"
require_file "$OPENCLAW_CFG/openclaw-config.json"

log "Aligning ownership with container runtime user"
cd "$OPENCLAW_DIR"
OC_UID="$(docker compose run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -u openclaw' | tr -d '\r' | tail -n 1)"
OC_GID="$(docker compose run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -g openclaw' | tr -d '\r' | tail -n 1)"
if ! [[ "$OC_UID" =~ ^[0-9]+$ ]] || ! [[ "$OC_GID" =~ ^[0-9]+$ ]]; then
  echo "Failed to resolve openclaw uid/gid from image (uid='${OC_UID}' gid='${OC_GID}')." >&2
  exit 1
fi
chown -R "${OC_UID}:${OC_GID}" "$OPENCLAW_CFG"
chmod 600 "$OPENCLAW_CFG/openclaw.json" "$OPENCLAW_CFG/openclaw-config.json"

log "Syncing runtime envs"
if [ -x /usr/local/sbin/sync-sentinel-env.sh ]; then
  /usr/local/sbin/sync-sentinel-env.sh
else
  log "WARN: /usr/local/sbin/sync-sentinel-env.sh missing; skipping Sentinel env sync"
fi

if [ -f "/root/openclaw/.env" ]; then
  BRAVE_API_KEY="$(grep '^BRAVE_API_KEY=' /root/openclaw/.env | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"
  BRAVE_KEY_LEN="${#BRAVE_API_KEY}"
  if [ -z "$BRAVE_API_KEY" ] || [[ "$BRAVE_API_KEY" == REPLACE_* ]]; then
    log "WARN: BRAVE_API_KEY missing/placeholder in /root/openclaw/.env (ai_daily_brief will report provider unconfigured)"
  elif [ "$BRAVE_KEY_LEN" -lt 20 ]; then
    log "WARN: BRAVE_API_KEY appears invalid (len=${BRAVE_KEY_LEN}); Brave API will fail until corrected"
  else
    log "Brave provider key detected for ai_daily_brief grounding"
  fi
else
  log "WARN: /root/openclaw/.env missing; cannot validate BRAVE_API_KEY"
fi

if [ -x /usr/local/sbin/sync-openclaw-config.sh ]; then
  OPENCLAW_CONFIG_UID="$OC_UID" OPENCLAW_CONFIG_GID="$OC_GID" /usr/local/sbin/sync-openclaw-config.sh
else
  log "WARN: /usr/local/sbin/sync-openclaw-config.sh missing; using project-local fallback"
  OPENCLAW_CONFIG_UID="$OC_UID" OPENCLAW_CONFIG_GID="$OC_GID" bash "$PROJECT_DIR/infrastructure/sync-openclaw-config.sh" \
    "/root/openclaw/.env" \
    "$PROJECT_DIR/openclaw/openclaw-config.json"
fi

# sync-openclaw-config.sh writes config files as root; force ownership back to runtime uid/gid.
chown -R "${OC_UID}:${OC_GID}" "$OPENCLAW_CFG"
chmod 600 "$OPENCLAW_CFG/openclaw.json" "$OPENCLAW_CFG/openclaw-config.json"

log "Restarting services"
docker compose up -d --force-recreate
systemctl daemon-reload
systemctl restart sentinel

log "Waiting for OpenClaw gateway health"
for i in $(seq 1 "$WAIT_ATTEMPTS"); do
  HS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' openclaw-openclaw-gateway-1 2>/dev/null || echo unknown)"
  log "attempt ${i}/${WAIT_ATTEMPTS}: gateway health=${HS}"
  if [ "$HS" = "healthy" ]; then
    break
  fi
  sleep "$WAIT_SECONDS"
done

log "Final health check"
"$PROJECT_DIR/infrastructure/health-check.sh"

if [ -f "/root/openclaw/.env" ]; then
  GW_TOKEN_LINES="$(grep -c '^OPENCLAW_GATEWAY_TOKEN=' /root/openclaw/.env || true)"
  if [ "${GW_TOKEN_LINES}" -gt 1 ]; then
    log "WARN: multiple OPENCLAW_GATEWAY_TOKEN entries in /root/openclaw/.env (using last line)"
  fi
  GW_TOKEN_ENV="$(grep '^OPENCLAW_GATEWAY_TOKEN=' /root/openclaw/.env | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"
  GW_TOKEN_CFG="$(python3 - <<'PY'
import json
path='/root/.openclaw/openclaw.json'
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print((((data.get('gateway') or {}).get('auth') or {}).get('token') or '').strip())
except Exception:
    print('')
PY
)"
  if [ -n "$GW_TOKEN_CFG" ] && [ -n "$GW_TOKEN_ENV" ] && [ "$GW_TOKEN_CFG" != "$GW_TOKEN_ENV" ]; then
    log "WARN: gateway.auth.token mismatch between runtime config and env; preferring runtime config token"
  fi
  GW_TOKEN="$GW_TOKEN_CFG"
  if [ -z "$GW_TOKEN" ]; then
    GW_TOKEN="$GW_TOKEN_ENV"
  fi

  if [ -n "$GW_TOKEN" ]; then
    HEALTH_AUTH_SOURCE=""
    health_call() {
      local token="$1"
      docker exec openclaw-openclaw-gateway-1 node openclaw.mjs gateway call health --url ws://127.0.0.1:18789 --token "$token" --json >/tmp/aibrief-post-health.json 2>/tmp/aibrief-post-health.err
    }

    if health_call "$GW_TOKEN"; then
      HEALTH_AUTH_SOURCE="runtime-config"
    elif [ -n "$GW_TOKEN_ENV" ] && [ "$GW_TOKEN_ENV" != "$GW_TOKEN" ] && health_call "$GW_TOKEN_ENV"; then
      HEALTH_AUTH_SOURCE="env-fallback"
    fi

    if [ -n "$HEALTH_AUTH_SOURCE" ]; then
      if [ "$HEALTH_AUTH_SOURCE" = "env-fallback" ]; then
        log "WARN: post-rollout health RPC required env fallback token; runtime config token may be stale"
      fi
      TG_STATUS="$(python3 - <<'PY'
import json
with open('/tmp/aibrief-post-health.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
telegram = ((data.get('channels') or {}).get('telegram') or {})
print("running=" + str(bool(telegram.get('running'))).lower())
print("tokenSource=" + str(telegram.get('tokenSource')))
print("lastError=" + str(telegram.get('lastError')))
PY
)"
      TG_RUNNING="$(echo "$TG_STATUS" | sed -n 's/^running=//p' | tail -n1)"
      TG_TOKEN_SOURCE="$(echo "$TG_STATUS" | sed -n 's/^tokenSource=//p' | tail -n1)"
      TG_LAST_ERROR="$(echo "$TG_STATUS" | sed -n 's/^lastError=//p' | tail -n1)"
      if [ "$TG_RUNNING" = "true" ]; then
        log "Telegram ingest runtime is running (tokenSource=${TG_TOKEN_SOURCE})"
      else
        log "WARN: Telegram ingest runtime reports running=false (tokenSource=${TG_TOKEN_SOURCE}; lastError=${TG_LAST_ERROR})"
        if [ "$TG_TOKEN_SOURCE" = "none" ]; then
          log "WARN: Telegram token not loaded by gateway config. Re-sync with infrastructure/sync-openclaw-config.sh and recreate container."
        fi
      fi
      if [ "$TG_TOKEN_SOURCE" = "none" ]; then
        TG_RUNTIME_DEBUG="$(docker exec openclaw-openclaw-gateway-1 node -e 'const fs=require(\"fs\");const p=\"/home/node/.openclaw/openclaw.json\";const trim=(v)=>typeof v===\"string\"?v.trim():\"\";try{const d=JSON.parse(fs.readFileSync(p,\"utf8\"));const tg=(d.channels&&d.channels.telegram)||{};const acct=(tg.accounts&&tg.accounts.default)||{};console.log(\"top.botToken.len=\"+trim(tg.botToken).length);console.log(\"top.tokenFile=\"+trim(tg.tokenFile));console.log(\"account.default.botToken.len=\"+trim(acct.botToken).length);console.log(\"account.default.tokenFile=\"+trim(acct.tokenFile));}catch(err){console.log(\"runtime.config.read.error=\"+String(err));}')" || true
        if [ -n "$TG_RUNTIME_DEBUG" ]; then
          log "Telegram runtime token diagnostics:"
          printf '%s\n' "$TG_RUNTIME_DEBUG" | sed 's/^/[aibrief-rollout]   /'
        fi
      fi
    else
      log "WARN: unable to perform post-rollout gateway health call"
      tail -n 5 /tmp/aibrief-post-health.err || true
    fi
  else
    log "WARN: OPENCLAW_GATEWAY_TOKEN missing in both runtime config and env; skipping gateway health RPC"
  fi
fi

log "Rollout complete for ref ${CURRENT_REF}."
log "Telegram smoke test: send /ai_daily_brief status then /ai_daily_brief top5 (or /ai_daily_brief_top5 compatibility alias)."
log "Set/update channel routing: $PROJECT_DIR/infrastructure/set-aibrief-output-channel.sh @dandailybriefAI"
log "Optional local test: $PROJECT_DIR/infrastructure/aibrief-smoke-test.sh"
log "If provider is unconfigured: set BRAVE_API_KEY in /root/openclaw/.env, then rerun rollout + smoke test."
