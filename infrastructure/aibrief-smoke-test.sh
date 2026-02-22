#!/usr/bin/env bash
# Smoke test for AI Daily Brief wiring on VPS.
set -euo pipefail

OPENCLAW_DIR="${OPENCLAW_DIR:-/root/openclaw}"
PROJECT_DIR="${PROJECT_DIR:-/root/openclaw-project}"
STATE_FILE="${STATE_FILE:-/root/.openclaw/workspace/logs/ai-brief-state.json}"
ENV_FILE="${ENV_FILE:-/root/openclaw/.env}"

PASS=0
FAIL=0
WARN=0

pass() { echo "[PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }
warn() { echo "[WARN] $1"; WARN=$((WARN + 1)); }

printf '=== AI Daily Brief Smoke Test ===\n'
printf 'Date: %s\n\n' "$(date -u)"

if [ -f "/root/.openclaw/skills/ai-daily-brief/SKILL.md" ]; then
  pass "Canonical AI brief skill exists (/root/.openclaw/skills/ai-daily-brief/SKILL.md)"
else
  fail "Canonical AI brief skill missing (/root/.openclaw/skills/ai-daily-brief/SKILL.md)"
fi

STALE_SKILLS=()
for legacy in \
  aibrief \
  aibrief_morning \
  aibrief_evening \
  aibrief_top5 \
  aibrief_builder \
  aibrief_watchlist \
  aibrief_status; do
  if [ -d "/root/.openclaw/skills/$legacy" ]; then
    STALE_SKILLS+=("$legacy")
  fi
done
if [ "${#STALE_SKILLS[@]}" -gt 0 ]; then
  fail "Deprecated alias skill folders still present: ${STALE_SKILLS[*]}"
else
  pass "No deprecated /aibrief* alias skill folders on runtime"
fi

if docker inspect openclaw-openclaw-gateway-1 >/dev/null 2>&1; then
  pass "OpenClaw gateway container exists"
else
  fail "OpenClaw gateway container not found"
fi

HS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' openclaw-openclaw-gateway-1 2>/dev/null || echo unknown)"
if [ "$HS" = "healthy" ]; then
  pass "OpenClaw gateway health is healthy"
else
  fail "OpenClaw gateway health is ${HS}"
fi

HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/__openclaw__/canvas/ 2>/dev/null || true)"
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "401" ]; then
  pass "Fallback endpoint reachable (${HTTP_CODE})"
else
  warn "Fallback endpoint unexpected status (${HTTP_CODE:-000})"
fi

if [ -f "$ENV_FILE" ]; then
  pass "Env file exists ($ENV_FILE)"
else
  fail "Missing env file ($ENV_FILE)"
fi

if [ -f "$STATE_FILE" ]; then
  pass "AI brief state file exists ($STATE_FILE)"
  STATE_INFO="$(python3 - <<'PY' "$STATE_FILE"
import json, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
print('State version:', data.get('version'))
print('Last successful morning:', (data.get('last_successful_run') or {}).get('morning'))
print('Last successful evening:', (data.get('last_successful_run') or {}).get('evening'))
print('Watchlist size:', len(data.get('watchlist') or []))
target = ((data.get('config') or {}).get('output_channel')) or data.get('output_channel')
provider = ((data.get('config') or {}).get('provider')) or ((data.get('providers') or {}).get('primary'))
brave_cfg = ((data.get('config') or {}).get('brave_llm_context') or {})
print('Provider:', provider)
print('Brave endpoint:', brave_cfg.get('endpoint'))
print('Brave threshold mode:', brave_cfg.get('context_threshold_mode'))
print('Brave max tokens:', brave_cfg.get('maximum_number_of_tokens'))
print('Output channel target:', target)
print(target or "")
PY
)"
  echo "$STATE_INFO" | sed '$d'
  if echo "$STATE_INFO" | grep -q 'Provider: brave_llm_context'; then
    pass "State provider is set to brave_llm_context"
  else
    warn "State provider is not brave_llm_context (check config.provider in state file)"
  fi
  OUTPUT_TARGET="$(echo "$STATE_INFO" | tail -n1 | tr -d '\r')"
  if [ -n "$OUTPUT_TARGET" ]; then
    pass "AI brief output channel configured ($OUTPUT_TARGET)"
  else
    warn "AI brief output channel not configured (will deliver to originating chat)"
  fi
else
  fail "AI brief state file missing ($STATE_FILE)"
fi

if [ -f "$ENV_FILE" ]; then
  GW_TOKEN="$(grep '^OPENCLAW_GATEWAY_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  SENTINEL_TG_TOKEN="$(grep '^SENTINEL_TELEGRAM_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  BRAVE_API_KEY="$(grep '^BRAVE_API_KEY=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"

  if [ -n "$GW_TOKEN" ]; then
    if docker exec openclaw-openclaw-gateway-1 node openclaw.mjs gateway call health --url ws://127.0.0.1:18789 --token "$GW_TOKEN" --json >/tmp/aibrief-health.json 2>/tmp/aibrief-health.err; then
      pass "Gateway health call authenticated"
      python3 - <<'PY'
import json
with open('/tmp/aibrief-health.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print('Gateway OK:', data.get('ok'))
print('Default agent:', data.get('defaultAgentId'))
print('Telegram configured:', (((data.get('channels') or {}).get('telegram') or {}).get('configured')))
PY
    else
      fail "Gateway health call failed: $(tail -n 1 /tmp/aibrief-health.err)"
    fi
  else
    fail "OPENCLAW_GATEWAY_TOKEN missing"
  fi

  if [ -n "$TG_TOKEN" ]; then
    TG_META="$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getMe" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok:"+str((d.get("result") or {}).get("username","?")) if d.get("ok") else "bad")' 2>/dev/null || true)"
    if [[ "$TG_META" == ok:* ]]; then
      pass "OpenClaw Telegram token validated via getMe (${TG_META#ok:})"
    else
      fail "OpenClaw Telegram token failed getMe"
    fi
  else
    fail "OPENCLAW_TELEGRAM_TOKEN missing"
  fi

  if [ -n "$TG_TOKEN" ]; then
    CMDS_MISSING="$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getMyCommands" | python3 -c 'import json,sys; d=json.load(sys.stdin); cmds={(c.get("command") or "") for c in (d.get("result") or [])}; required=["ai_daily_brief","ai_daily_brief_morning","ai_daily_brief_evening","ai_daily_brief_top5","ai_daily_brief_builder","ai_daily_brief_watchlist","ai_daily_brief_status"]; missing=[c for c in required if c not in cmds]; print(",".join(missing))' 2>/dev/null || true)"
    if [ -z "$CMDS_MISSING" ]; then
      pass "Telegram native AI brief commands are registered (/ai_daily_brief + compatibility aliases)"
    else
      fail "Telegram native AI brief commands missing: ${CMDS_MISSING} (check nativeSkills config + restart)"
    fi
  fi

  if [ -n "$SENTINEL_TG_TOKEN" ]; then
    STG_META="$(curl -s "https://api.telegram.org/bot${SENTINEL_TG_TOKEN}/getMe" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok:"+str((d.get("result") or {}).get("username","?")) if d.get("ok") else "bad")' 2>/dev/null || true)"
    if [[ "$STG_META" == ok:* ]]; then
      pass "Sentinel Telegram token validated via getMe (${STG_META#ok:})"
    else
      fail "Sentinel Telegram token failed getMe"
    fi
  else
    fail "SENTINEL_TELEGRAM_TOKEN missing"
  fi

  if [ -n "$TG_TOKEN" ] && [ -n "$SENTINEL_TG_TOKEN" ]; then
    if [ "$TG_TOKEN" = "$SENTINEL_TG_TOKEN" ]; then
      fail "OPENCLAW_TELEGRAM_TOKEN and SENTINEL_TELEGRAM_TOKEN are identical"
    else
      pass "OpenClaw and Sentinel Telegram tokens are distinct"
    fi
  fi

  if [ -z "$BRAVE_API_KEY" ] || [[ "$BRAVE_API_KEY" == REPLACE_* ]]; then
    fail "BRAVE_API_KEY missing/placeholder (AI Daily Brief web grounding unavailable)"
  else
    BRAVE_HTTP_CODE="$(curl -sS --max-time 30 --compressed \
      -o /tmp/aibrief-brave-context.json \
      -w '%{http_code}' \
      -H 'accept: application/json' \
      -H 'Accept-Encoding: gzip' \
      -H "X-Subscription-Token: ${BRAVE_API_KEY}" \
      --get \
      --data-urlencode 'q=latest ai model release updates' \
      --data-urlencode 'count=5' \
      --data-urlencode 'maximum_number_of_tokens=2048' \
      --data-urlencode 'context_threshold_mode=balanced' \
      'https://api.search.brave.com/res/v1/llm/context' \
      2>/tmp/aibrief-brave-context.err || true)"
    if [ "$BRAVE_HTTP_CODE" = "200" ]; then
      BRAVE_GENERIC_COUNT="$(python3 - <<'PY'
import json
with open('/tmp/aibrief-brave-context.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
generic = (((data.get('grounding') or {}).get('generic')) or [])
print(len(generic))
PY
)"
      pass "Brave LLM Context API reachable (grounding.generic items: ${BRAVE_GENERIC_COUNT})"
    else
      BRAVE_ERROR="$(python3 - <<'PY'
import json
try:
    with open('/tmp/aibrief-brave-context.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print((data.get('error') or {}).get('message') or data.get('message') or 'unknown error')
except Exception:
    print('no-json-error-body')
PY
)"
      fail "Brave LLM Context API probe failed (HTTP ${BRAVE_HTTP_CODE}): ${BRAVE_ERROR}"
    fi
  fi
fi

if ls -1 /root/.openclaw/workspace/outputs/summaries/ai-brief-*.md >/dev/null 2>&1; then
  LATEST="$(ls -1t /root/.openclaw/workspace/outputs/summaries/ai-brief-*.md | head -n 1)"
  pass "AI brief output exists ($LATEST)"
else
  warn "No ai-brief-*.md output yet (run /ai_daily_brief in Telegram to generate first brief)"
fi

if docker compose -f "$OPENCLAW_DIR/docker-compose.yml" logs --tail=120 openclaw-gateway | grep -Eiq 'telegram.*(404|unauthorized|device token mismatch)'; then
  warn "Recent Telegram channel warnings detected in OpenClaw logs"
else
  pass "No critical Telegram channel errors in recent logs"
fi

echo ""
echo "Summary: ${PASS} passed, ${FAIL} failed, ${WARN} warnings"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
