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

WORKSPACE_BOOTSTRAP_MISSING=()
for bootstrap in AGENTS.md SOUL.md TOOLS.md HEARTBEAT.md; do
  if [ ! -f "/root/.openclaw/workspace/$bootstrap" ]; then
    WORKSPACE_BOOTSTRAP_MISSING+=("$bootstrap")
  fi
done
if [ "${#WORKSPACE_BOOTSTRAP_MISSING[@]}" -gt 0 ]; then
  fail "Workspace bootstrap files missing: ${WORKSPACE_BOOTSTRAP_MISSING[*]} (expected under /root/.openclaw/workspace)"
else
  pass "Workspace bootstrap files present (/root/.openclaw/workspace/{AGENTS,SOUL,TOOLS,HEARTBEAT}.md)"
fi

if [ -f "/root/.openclaw/workspace/SOUL.md" ]; then
  if grep -Fq 'Execute `/ai_daily_brief*` commands directly in the current lane using the `ai-daily-brief*` skills.' /root/.openclaw/workspace/SOUL.md; then
    pass "SOUL policy enforces direct in-lane execution for /ai_daily_brief*"
  else
    fail "SOUL policy missing direct in-lane /ai_daily_brief* execution rule (runtime may still force sub-agent path)"
  fi
fi

if [ -f "/root/.openclaw/workspace/AGENTS.md" ]; then
  if grep -Fq 'do not require sub-agent spawning for `/ai_daily_brief*` slash commands' /root/.openclaw/workspace/AGENTS.md; then
    pass "AGENTS policy confirms /ai_daily_brief* does not require sub-agent spawn"
  else
    fail "AGENTS policy missing non-sub-agent /ai_daily_brief* execution mode"
  fi
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
  GW_TOKEN_LINES="$(grep -c '^OPENCLAW_GATEWAY_TOKEN=' "$ENV_FILE" || true)"
  if [ "${GW_TOKEN_LINES}" -gt 1 ]; then
    warn "Multiple OPENCLAW_GATEWAY_TOKEN entries found in $ENV_FILE (using last line)"
  fi
  GW_TOKEN_ENV="$(grep '^OPENCLAW_GATEWAY_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  GW_TOKEN_CFG="$(python3 - <<'PY'
import json
path='/root/.openclaw/openclaw.json'
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    token = (((data.get('gateway') or {}).get('auth') or {}).get('token') or '').strip()
    print(token)
except Exception:
    print('')
PY
)"
  if [ -n "$GW_TOKEN_CFG" ] && [ -n "$GW_TOKEN_ENV" ] && [ "$GW_TOKEN_CFG" != "$GW_TOKEN_ENV" ]; then
    warn "Gateway auth token mismatch between /root/.openclaw/openclaw.json and $ENV_FILE (preferring runtime config token)"
  fi
  GW_TOKEN="$GW_TOKEN_CFG"
  if [ -z "$GW_TOKEN" ]; then
    GW_TOKEN="$GW_TOKEN_ENV"
  fi

  TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  if [ -z "$TG_TOKEN" ]; then
    TG_TOKEN="$(grep '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  fi
  SENTINEL_TG_TOKEN="$(grep '^SENTINEL_TELEGRAM_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"
  BRAVE_API_KEY="$(grep '^BRAVE_API_KEY=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//')"

  TG_CFG_RUNTIME="$(python3 - <<'PY'
import json
path='/root/.openclaw/openclaw.json'
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    tg = ((data.get('channels') or {}).get('telegram') or {})
    token = (tg.get('botToken') or '').strip()
    token_file = (tg.get('tokenFile') or '').strip()
    acct = ((tg.get('accounts') or {}).get('default') or {})
    acct_token = (acct.get('botToken') or '').strip()
    acct_token_file = (acct.get('tokenFile') or '').strip()
    ok = bool(token or acct_token or token_file or acct_token_file)
    print('yes' if ok else 'no')
    print(token_file)
    print(acct_token_file)
except Exception:
    print('no')
    print('')
    print('')
PY
)"
  TG_CFG_PRESENT="$(echo "$TG_CFG_RUNTIME" | sed -n '1p')"
  TG_CFG_TOKEN_FILE="$(echo "$TG_CFG_RUNTIME" | sed -n '2p')"
  TG_CFG_ACCOUNT_TOKEN_FILE="$(echo "$TG_CFG_RUNTIME" | sed -n '3p')"
  if [ "$TG_CFG_PRESENT" = "yes" ]; then
    pass "Runtime config has Telegram auth material (botToken/tokenFile) at channels.telegram(.accounts.default)"
  else
    fail "Runtime config missing Telegram auth material (botToken/tokenFile) in openclaw.json"
  fi

  CHECKED_TOKEN_FILE=""
  check_token_file() {
    local token_file_path="$1"
    if [ -z "$token_file_path" ]; then
      return
    fi
    if [ "$token_file_path" = "$CHECKED_TOKEN_FILE" ]; then
      return
    fi
    CHECKED_TOKEN_FILE="$token_file_path"
    if docker exec -e TOKEN_FILE_PATH="$token_file_path" openclaw-openclaw-gateway-1 sh -lc 'test -r "$TOKEN_FILE_PATH"'; then
      pass "Gateway runtime user can read Telegram tokenFile (${token_file_path})"
    else
      fail "Gateway runtime user cannot read Telegram tokenFile (${token_file_path})"
    fi
  }
  check_token_file "$TG_CFG_TOKEN_FILE"
  check_token_file "$TG_CFG_ACCOUNT_TOKEN_FILE"

  if [ "$TG_CFG_PRESENT" = "yes" ] && [ -z "$TG_CFG_TOKEN_FILE" ] && [ -z "$TG_CFG_ACCOUNT_TOKEN_FILE" ]; then
    warn "Runtime Telegram config uses botToken only; tokenFile fallback is not configured"
  fi

  TG_DM_RUNTIME="$(python3 - <<'PY'
import json
path='/root/.openclaw/openclaw.json'
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    tg = ((data.get('channels') or {}).get('telegram') or {})
    dm_policy = str(tg.get('dmPolicy') or '').strip().lower()
    allow = tg.get('allowFrom')
    normalized = []
    if isinstance(allow, list):
        for entry in allow:
            value = str(entry).strip()
            if not value:
                continue
            if value not in normalized:
                normalized.append(value)
    print(dm_policy)
    print(",".join(normalized))
    print(len(normalized))
except Exception:
    print('')
    print('')
    print('0')
PY
)"
  TG_DM_POLICY="$(echo "$TG_DM_RUNTIME" | sed -n '1p')"
  TG_ALLOW_FROM="$(echo "$TG_DM_RUNTIME" | sed -n '2p')"
  TG_ALLOW_COUNT="$(echo "$TG_DM_RUNTIME" | sed -n '3p')"
  if [ "${TG_DM_POLICY}" = "pairing" ] && [ "${TG_ALLOW_COUNT}" = "0" ]; then
    fail "Telegram dmPolicy=pairing with empty allowFrom (DM skill commands are gated until pairing approval). Fix: set OPENCLAW_TELEGRAM_DM_POLICY=allowlist + OPENCLAW_TELEGRAM_ALLOW_FROM=<your_telegram_id>, or approve pending pair codes via: docker exec openclaw-openclaw-gateway-1 node openclaw.mjs pairing list --channel telegram"
  elif [ "${TG_ALLOW_COUNT}" != "0" ]; then
    pass "Telegram DM allowFrom configured (${TG_ALLOW_FROM})"
  else
    warn "Telegram DM allowFrom is empty (native command authorization may block skill invocation)"
  fi

  if docker exec openclaw-openclaw-gateway-1 sh -lc 'test -r /home/node/.openclaw/openclaw.json'; then
    pass "Gateway runtime user can read /home/node/.openclaw/openclaw.json"
  else
    fail "Gateway runtime user cannot read /home/node/.openclaw/openclaw.json (ownership/permissions drift)"
  fi

  TG_ENV_VISIBLE="$(docker exec openclaw-openclaw-gateway-1 sh -lc 'if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || [ -n "${OPENCLAW_TELEGRAM_TOKEN:-}" ]; then echo yes; else echo no; fi' 2>/dev/null || echo no)"
  if [ "$TG_ENV_VISIBLE" = "yes" ]; then
    pass "Gateway container has Telegram bot token in environment"
  else
    warn "Gateway container Telegram env token is empty (config botToken may still work, but env fallback is unavailable)"
  fi

  if [ -n "$GW_TOKEN" ]; then
    HEALTH_AUTH_SOURCE=""
    health_call() {
      local token="$1"
      docker exec openclaw-openclaw-gateway-1 node openclaw.mjs gateway call health --url ws://127.0.0.1:18789 --token "$token" --json >/tmp/aibrief-health.json 2>/tmp/aibrief-health.err
    }
    channels_status_call() {
      local token="$1"
      docker exec openclaw-openclaw-gateway-1 node openclaw.mjs gateway call channels.status --url ws://127.0.0.1:18789 --token "$token" --json >/tmp/aibrief-channels.json 2>/tmp/aibrief-channels.err
    }

    if health_call "$GW_TOKEN"; then
      HEALTH_AUTH_SOURCE="runtime-config"
    elif [ -n "$GW_TOKEN_ENV" ] && [ "$GW_TOKEN_ENV" != "$GW_TOKEN" ] && health_call "$GW_TOKEN_ENV"; then
      HEALTH_AUTH_SOURCE="env-fallback"
    fi

    if [ -n "$HEALTH_AUTH_SOURCE" ]; then
      if [ "$HEALTH_AUTH_SOURCE" = "env-fallback" ]; then
        pass "Gateway health call authenticated (env fallback token)"
        warn "Gateway health auth required env fallback token; runtime config gateway.auth.token may be stale"
      else
        pass "Gateway health call authenticated"
      fi
      python3 - <<'PY'
import json
with open('/tmp/aibrief-health.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print('Gateway OK:', data.get('ok'))
print('Default agent:', data.get('defaultAgentId'))
PY
      if channels_status_call "$GW_TOKEN" || { [ -n "$GW_TOKEN_ENV" ] && [ "$GW_TOKEN_ENV" != "$GW_TOKEN" ] && channels_status_call "$GW_TOKEN_ENV"; }; then
        TG_RUNTIME="$(python3 - <<'PY'
import json
with open('/tmp/aibrief-channels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
default_id = str(((data.get('channelDefaultAccountId') or {}).get('telegram')) or 'default')
accounts = ((data.get('channelAccounts') or {}).get('telegram') or [])
selected = None
for item in accounts:
    if str(item.get('accountId') or '') == default_id:
        selected = item
        break
if selected is None and accounts:
    selected = accounts[0]
selected = selected or {}
print('Telegram accountId:', str(selected.get('accountId') or default_id))
print('Telegram configured:', bool(selected.get('configured')))
print('Telegram running:', bool(selected.get('running')))
print('Telegram tokenSource:', str(selected.get('tokenSource') or 'none'))
print('Telegram lastError:', selected.get('lastError'))
print('Telegram lastInboundAt:', selected.get('lastInboundAt'))
print('Telegram lastOutboundAt:', selected.get('lastOutboundAt'))
print('__ACCOUNT_ID__=' + str(selected.get('accountId') or default_id))
print('__RUNNING__=' + str(bool(selected.get('running'))).lower())
print('__TOKENSOURCE__=' + str(selected.get('tokenSource') or 'none'))
print('__LASTINBOUND__=' + str(selected.get('lastInboundAt')))
print('__LASTOUTBOUND__=' + str(selected.get('lastOutboundAt')))
PY
)"
        echo "$TG_RUNTIME" | grep -Ev '^__ACCOUNT_ID__=|^__RUNNING__=|^__TOKENSOURCE__=|^__LASTINBOUND__=|^__LASTOUTBOUND__='
        TG_ACCOUNT_ID="$(echo "$TG_RUNTIME" | sed -n 's/^__ACCOUNT_ID__=//p' | tail -n1)"
        TELEGRAM_RUNNING="$(echo "$TG_RUNTIME" | sed -n 's/^__RUNNING__=//p' | tail -n1)"
        TELEGRAM_TOKEN_SOURCE="$(echo "$TG_RUNTIME" | sed -n 's/^__TOKENSOURCE__=//p' | tail -n1)"
        TG_LAST_INBOUND_AT="$(echo "$TG_RUNTIME" | sed -n 's/^__LASTINBOUND__=//p' | tail -n1)"
        TG_LAST_OUTBOUND_AT="$(echo "$TG_RUNTIME" | sed -n 's/^__LASTOUTBOUND__=//p' | tail -n1)"
        if [ "$TELEGRAM_RUNNING" = "true" ]; then
          pass "Telegram ingest runtime is running"
        else
          fail "Telegram ingest runtime is not running (channels.status reports running=false)"
        fi
        if [ "$TELEGRAM_TOKEN_SOURCE" = "none" ]; then
          fail "Gateway Telegram tokenSource=none (channels.status account resolution failed to load token)"
          TG_RUNTIME_DEBUG="$(docker exec openclaw-openclaw-gateway-1 node -e 'const fs=require("fs");const p="/home/node/.openclaw/openclaw.json";const trim=(v)=>typeof v==="string"?v.trim():"";try{const d=JSON.parse(fs.readFileSync(p,"utf8"));const tg=(d.channels&&d.channels.telegram)||{};const acct=(tg.accounts&&tg.accounts.default)||{};console.log("runtime.top.botToken.len="+trim(tg.botToken).length);console.log("runtime.top.tokenFile="+trim(tg.tokenFile));console.log("runtime.account.default.botToken.len="+trim(acct.botToken).length);console.log("runtime.account.default.tokenFile="+trim(acct.tokenFile));}catch(err){console.log("runtime.config.read.error="+String(err));}')" || true
          if [ -n "$TG_RUNTIME_DEBUG" ]; then
            echo "$TG_RUNTIME_DEBUG" | sed 's/^/[INFO] /'
          fi
        else
          pass "Gateway Telegram token source is ${TELEGRAM_TOKEN_SOURCE}"
        fi
        TG_OFFSET_FILE="/root/.openclaw/telegram/update-offset-${TG_ACCOUNT_ID:-default}.json"
        if [ -f "$TG_OFFSET_FILE" ]; then
          TG_OFFSET_LAST_UPDATE_ID="$(TG_OFFSET_FILE="$TG_OFFSET_FILE" python3 - <<'PY'
import json
import os
path = os.environ.get('TG_OFFSET_FILE', '')
try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    value = data.get('lastUpdateId')
    print(value if value is not None else '')
except Exception:
    print('')
PY
)"
          echo "Telegram update offset file: ${TG_OFFSET_FILE} (lastUpdateId=${TG_OFFSET_LAST_UPDATE_ID:-unknown})"
          if [ "$TELEGRAM_RUNNING" = "true" ] && { [ -z "$TG_LAST_INBOUND_AT" ] || [ "$TG_LAST_INBOUND_AT" = "None" ] || [ "$TG_LAST_INBOUND_AT" = "null" ]; }; then
            warn "Telegram has no inbound activity yet; stale update offset can silently skip commands. If commands do not trigger, run: /root/openclaw-project/infrastructure/reset-telegram-offset.sh ${TG_ACCOUNT_ID:-default}"
          fi
        fi
      else
        warn "channels.status call failed; skipping Telegram runtime assertions (health snapshot does not include live channel runtime)"
      fi
    else
      fail "Gateway health call failed: $(tail -n 1 /tmp/aibrief-health.err)"
    fi
  else
    fail "OPENCLAW_GATEWAY_TOKEN missing (both runtime config and env)"
  fi

  if [ -n "$TG_TOKEN" ]; then
    TG_LEN="${#TG_TOKEN}"
    if [ "$TG_LEN" -lt 30 ]; then
      fail "OPENCLAW_TELEGRAM_TOKEN appears invalid (len=${TG_LEN})"
    fi
    TG_META="$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getMe" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok:"+str((d.get("result") or {}).get("username","?")) if d.get("ok") else "bad")' 2>/dev/null || true)"
    if [[ "$TG_META" == ok:* ]]; then
      pass "OpenClaw Telegram token validated via getMe (${TG_META#ok:})"
    else
      fail "OpenClaw Telegram token failed getMe"
    fi
  else
    fail "OPENCLAW_TELEGRAM_TOKEN missing"
  fi

  if [ -n "$TG_TOKEN" ] && [ "${TG_LEN:-0}" -ge 30 ]; then
    WEBHOOK_INFO="$(curl -sf "https://api.telegram.org/bot${TG_TOKEN}/getWebhookInfo" 2>/dev/null || true)"
    WEBHOOK_URL="$(echo "$WEBHOOK_INFO" | python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    data={}
print(((data.get("result") or {}).get("url")) or "")
' 2>/dev/null || true)"
    WEBHOOK_PENDING="$(echo "$WEBHOOK_INFO" | python3 -c 'import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    data={}
print((data.get("result") or {}).get("pending_update_count") or 0)
' 2>/dev/null || echo 0)"
    if [ -n "$WEBHOOK_URL" ]; then
      fail "Active Telegram webhook blocks polling (url=${WEBHOOK_URL}, pending=${WEBHOOK_PENDING}). Fix: curl -sf \"https://api.telegram.org/bot\${TG_TOKEN}/deleteWebhook\""
    else
      pass "No active Telegram webhook (polling mode unblocked)"
    fi
  fi

  if [ -n "$TG_TOKEN" ]; then
    CMDS_MISSING="$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getMyCommands" | python3 -c 'import json,sys; d=json.load(sys.stdin); cmds={(c.get("command") or "") for c in (d.get("result") or [])}; required=["ai_daily_brief","ai_daily_brief_morning","ai_daily_brief_evening","ai_daily_brief_top5","ai_daily_brief_builder","ai_daily_brief_watchlist","ai_daily_brief_status"]; missing=[c for c in required if c not in cmds]; print(",".join(missing))' 2>/dev/null || true)"
    if [ -z "$CMDS_MISSING" ]; then
      pass "Telegram native AI brief commands are registered (/ai_daily_brief + compatibility aliases)"
    else
      fail "Telegram native AI brief commands missing: ${CMDS_MISSING} (check nativeSkills config + restart)"
    fi
  fi

  DUP_TRIGGER_ISSUES="$(python3 - <<'PY'
import glob
import os
import re

skills_root = "/root/openclaw-project/openclaw/skills"
targets = [
    "/ai_daily_brief",
    "/ai_daily_brief_morning",
    "/ai_daily_brief_evening",
    "/ai_daily_brief_top5",
    "/ai_daily_brief_builder",
    "/ai_daily_brief_watchlist",
    "/ai_daily_brief_status",
]
seen = {target: [] for target in targets}

for skill_path in sorted(glob.glob(os.path.join(skills_root, "*", "SKILL.md"))):
    skill_name = os.path.basename(os.path.dirname(skill_path))
    try:
        with open(skill_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except Exception:
        continue

    in_frontmatter = False
    fence_count = 0
    for raw in lines:
        line = raw.rstrip()
        if line.strip() == "---":
            fence_count += 1
            if fence_count == 1:
                in_frontmatter = True
                continue
            if fence_count == 2:
                break
        if not in_frontmatter:
            continue

        match = re.match(r'^\s*-\s*"(\/ai_daily_brief[^"]*)"\s*$', line)
        if not match:
            match = re.match(r"^\s*-\s*'(\/ai_daily_brief[^']*)'\s*$", line)
        if not match:
            match = re.match(r'^\s*-\s*(/ai_daily_brief\S*)\s*$', line)
        if not match:
            continue

        trigger = match.group(1).strip()
        if trigger in seen:
            seen[trigger].append(skill_name)

issues = []
for trigger in targets:
    owners = sorted(set(seen[trigger]))
    if len(owners) != 1:
        issues.append(f"{trigger}:{','.join(owners) if owners else 'none'}")

print("; ".join(issues))
PY
)"
  if [ -z "$DUP_TRIGGER_ISSUES" ]; then
    pass "AI brief slash triggers are uniquely mapped (no ambiguous duplicate trigger owners)"
  else
    fail "AI brief trigger mapping is ambiguous: ${DUP_TRIGGER_ISSUES}"
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
  elif [ "${#BRAVE_API_KEY}" -lt 20 ]; then
    fail "BRAVE_API_KEY appears invalid (len=${#BRAVE_API_KEY}); update /root/openclaw/.env with a real Brave token"
  else
    BRAVE_ENV_VISIBLE="$(docker exec openclaw-openclaw-gateway-1 sh -lc 'if [ -n "${BRAVE_API_KEY:-}" ]; then echo yes; else echo no; fi' 2>/dev/null || echo no)"
    if [ "$BRAVE_ENV_VISIBLE" = "yes" ]; then
      pass "Gateway container has BRAVE_API_KEY in environment"
    else
      fail "Gateway container BRAVE_API_KEY is empty (runtime provider will be unconfigured)"
    fi

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
    msg = (data.get('error') or {}).get('message') or data.get('message')
    if msg:
        print(msg)
    else:
        print(str(data)[:220])
except Exception:
    print('no-json-error-body')
PY
)"
      BRAVE_WEB_CODE="$(curl -sS --max-time 20 \
        -o /tmp/aibrief-brave-web.json \
        -w '%{http_code}' \
        -H 'accept: application/json' \
        -H "X-Subscription-Token: ${BRAVE_API_KEY}" \
        --get \
        --data-urlencode 'q=openai' \
        --data-urlencode 'count=1' \
        'https://api.search.brave.com/res/v1/web/search' \
        2>/tmp/aibrief-brave-web.err || true)"
      if [ "$BRAVE_WEB_CODE" = "200" ]; then
        warn "Brave LLM Context probe failed (HTTP ${BRAVE_HTTP_CODE}: ${BRAVE_ERROR}) but Brave Web Search is reachable. Likely missing LLM Context entitlement; AI brief should run in fallback/partial mode."
      else
        BRAVE_KEY_LEN="${#BRAVE_API_KEY}"
        BRAVE_WEB_ERROR="$(python3 - <<'PY'
import json
try:
    with open('/tmp/aibrief-brave-web.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    msg = (data.get('error') or {}).get('message') or data.get('message')
    if msg:
        print(msg)
    else:
        print(str(data)[:220])
except Exception:
    print('no-json-error-body')
PY
)"
        fail "Brave API probes failed (llm/context HTTP ${BRAVE_HTTP_CODE}: ${BRAVE_ERROR}; web/search HTTP ${BRAVE_WEB_CODE}: ${BRAVE_WEB_ERROR}; key_len=${BRAVE_KEY_LEN})"
      fi
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
