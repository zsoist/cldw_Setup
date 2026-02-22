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
  python3 - <<'PY' "$STATE_FILE"
import json, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
print('State version:', data.get('version'))
print('Last successful morning:', (data.get('last_successful_run') or {}).get('morning'))
print('Last successful evening:', (data.get('last_successful_run') or {}).get('evening'))
print('Watchlist size:', len(data.get('watchlist') or []))
PY
else
  fail "AI brief state file missing ($STATE_FILE)"
fi

if [ -f "$ENV_FILE" ]; then
  GW_TOKEN="$(grep '^OPENCLAW_GATEWAY_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"

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
    TG_OK="$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getMe" | python3 -c 'import json,sys; print("ok" if json.load(sys.stdin).get("ok") else "bad")' 2>/dev/null || true)"
    if [ "$TG_OK" = "ok" ]; then
      pass "OpenClaw Telegram token validated via getMe"
    else
      fail "OpenClaw Telegram token failed getMe"
    fi
  else
    fail "OPENCLAW_TELEGRAM_TOKEN missing"
  fi
fi

if ls -1 /root/.openclaw/workspace/outputs/summaries/ai-brief-*.md >/dev/null 2>&1; then
  LATEST="$(ls -1t /root/.openclaw/workspace/outputs/summaries/ai-brief-*.md | head -n 1)"
  pass "AI brief output exists ($LATEST)"
else
  warn "No ai-brief-*.md output yet (run /aibrief in Telegram to generate first brief)"
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
