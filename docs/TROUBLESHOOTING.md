# Troubleshooting Guide

> Last updated: 2026-03-09 (Discord-first + Sentinel Codex runtime). For codebase navigation, see `ARCHITECTURE.md`.

> **Model note:** OpenClaw uses `openai-codex/gpt-5.3-codex` (subscription-covered, OAuth) as default, including heartbeat. Sentinel uses `openai/gpt-5-codex` via the OpenAI Responses API. Flash references below are historical or optional rollback paths.

---

## Sentinel Issues (2026-03-02)

### `/cost today` shows "Permission denied" on api-cost-summary.json

**Symptom:** `/cost today` returns `Errno 13 Permission denied: '/var/log/sentinel/api-cost-summary.json'` but the file is owned by sentinel:sentinel with correct 640 permissions.

**Root cause:** The Edit tool (Claude Code) resets file ownership to `root:root`. When `/opt/sentinel/tools.py` or any `.py` file becomes root-owned with 640 permissions, the sentinel process (uid=999) can't read it. Python's import system raises `PermissionError` which gets caught by the cost_summary exception handler, producing a misleading error message pointing to the JSON file.

**Fix (deployed 2026-03-02):**
1. Immediate: `chown sentinel:sentinel /opt/sentinel/*.py /opt/sentinel/__pycache__/*.pyc`
2. Structural: Added `set_cost_tracker()` module-level pattern -- cost reads now use `APICostTracker.get_summary()` (thread-safe, in-memory) instead of raw `open()` on the JSON file

**Prevention:** Always run `chown sentinel:sentinel /opt/sentinel/*.py /opt/sentinel/__pycache__/*.pyc` after editing ANY Sentinel source file.

### HTTP health probe always returns 000

**Symptom:** `/openclaw` shows `HTTP: 000` even though the gateway is healthy.

**Root cause:** The probe used `subprocess.run(["curl", ...])` from the host to `http://127.0.0.1:18789/`. Despite port mapping being active (docker-proxy listening), the gateway resets all host HTTP connections. Gateway likely requires WebSocket upgrade or internal auth.

**Fix (deployed 2026-03-02):** Changed to `container.exec_run(["curl", "-sf", ...])` which runs curl INSIDE the container, matching Docker's own health check. Now returns 200.

### .pyc files owned by root cause silent import failures

**Symptom:** Sentinel starts but some features silently fail. No obvious error in logs.

**Root cause:** Python `.pyc` files in `__pycache__/` get created by whoever runs the Python process. If you run `python3 -c "import tools"` as root, the `.pyc` is created as `root:root 640`. When sentinel (uid=999) tries to import, it can't read the `.pyc`, falls back to source, but can't write a new `.pyc` over the root-owned one.

**Fix:** `chown sentinel:sentinel /opt/sentinel/__pycache__/*.pyc`

---

## Codex-Specific Issues

### Bot asks clarification questions instead of executing

**Symptom:** User says "top ai news" and bot responds with "Quick preference check: which scope?" or "Would you like..."

**Cause:** Codex (gpt-5.3-codex) is more conversational than Flash. Without explicit anti-clarification prompting, it tends to ask questions before executing.

**Fix (applied 2026-03-01):**
- SOUL.md: "NEVER ASK CLARIFICATION QUESTIONS" rule + "bias to action" directive
- SKILL.md: No-clarification constraint in `<constraints>` block + 14 anti-patterns
- 20 few-shot NL parsing examples to reduce ambiguity

If the issue recurs, check that SOUL.md and SKILL.md still contain these directives.

### Bot says "Understood. Running now." but produces no output

**Symptom:** Bot acknowledges the command but doesn't actually execute the skill.

**Cause:** Codex preamble behavior — it generates status messages as its first turn, then may stop before executing.

**Fix:** SOUL.md one-message rule: "No preambles like 'Sure!', 'Got it!', 'Let me...'" + SKILL.md anti-pattern: "Saying 'Understood', 'Running now' before executing — just execute silently."

### Gateway dies after SIGUSR1 config reload

**Symptom:** Container exits with code 0 after `docker kill --signal=SIGUSR1`. `on-failure:5` doesn't restart it.

**Cause:** SIGUSR1 triggers a "full process restart" for auth changes (like Codex OAuth). Exit code 0 is a clean exit, so `on-failure:5` doesn't auto-restart.

**Fix:**
```bash
# Safe restart pattern (always use this instead of SIGUSR1 for auth/model changes):
cd /root/openclaw && docker compose down && docker compose up -d

# Or use the reload helper (validates first, then SIGUSR1):
/root/.openclaw/reload-config.sh
```

### Token spiral / session exceeds 100K tokens

**Symptom:** Session becomes slow, context usage shows >100K tokens, or session crashes.

**Cause:** Codex's 266K context window allows sessions to accumulate far more context than Flash. Without safeguards, sessions can spiral.

**Fix (deployed):**
- SOUL.md: >100K input tokens → abort session
- SKILL.md: >100K input tokens → abort
- contextTokens: 65536 (hard cap)
- contextPruning: cache-ttl 3m
- Docker restart policy: on-failure:5 (prevents restart loops)
- tools.deny: blocks expensive tools (browser, canvas, web_fetch)

---

## Quick Diagnostics

```bash
# Full system health
systemctl is-active sentinel
docker ps --format "{{.Names}}: {{.Status}}"

# Sentinel logs (filtered)
journalctl -u sentinel --since "1 hour ago" --no-pager | grep -v "getUpdates\|200 OK\|HTTP Request"

# OpenClaw logs (filtered)
docker logs openclaw-openclaw-gateway-1 --since 1h 2>&1 | grep -v "web_search"

# Check if config was rejected on last reload
docker logs openclaw-openclaw-gateway-1 --since 5m 2>&1 | grep -i "invalid\|error\|EACCES\|permission"

# Validate openclaw.json before reloading
python3 -m json.tool /root/.openclaw/openclaw.json > /dev/null && echo "JSON valid"

# Reload OpenClaw config without restart
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1
sleep 3
docker logs openclaw-openclaw-gateway-1 --since 5s 2>&1 | grep -i "reload\|invalid\|error"
```

---

## OpenClaw Issues

### OpenClaw container won't start
```bash
# Check logs
docker compose logs openclaw-gateway

# Common causes:
# 1. Missing .env values — check all REPLACE_ placeholders are filled
# 2. Port conflict — check if 18789 is already in use: ss -tlnp | grep 18789
# 3. Docker build failed — rebuild: docker compose build --no-cache
```

### OpenClaw config reload silently ignored (`Invalid config` in logs)

**Symptom:** You edited `openclaw.json` and sent `SIGUSR1`, but behavior hasn't changed. Gateway logs show:
```
Invalid config at /home/node/.openclaw/openclaw.json:
- agents.defaults.compaction.mode: Invalid input
```

**Cause:** An invalid value was used for `compaction.mode`. The only valid values in this OpenClaw build are `"default"` and `"safeguard"`. The value `"aggressive"` does NOT exist in the schema and will always be rejected.

**Fix:**
```bash
# Check current value
python3 -c "import json; d=json.load(open('/root/.openclaw/openclaw.json')); print(d['agents']['defaults'].get('compaction'))"

# Fix it
python3 -c "
import json
with open('/root/.openclaw/openclaw.json') as f: d = json.load(f)
d['agents']['defaults']['compaction'] = {'mode': 'safeguard'}
with open('/root/.openclaw/openclaw.json', 'w') as f: json.dump(d, f, indent=2)
print('fixed')
"
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
chmod 640 /root/.openclaw/openclaw.json

# Reload
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1
sleep 3
docker logs openclaw-openclaw-gateway-1 --since 5s 2>&1 | grep -i "invalid\|error\|reload"
# No output = success (errors are logged, success is silent)
```

### `EACCES: permission denied` reading `openclaw.json`

**Symptom:** Gateway logs show:
```
config watcher error: Error: EACCES: permission denied, watch '/home/node/.openclaw/openclaw.json'
Failed to read config at /home/node/.openclaw/openclaw.json Error: EACCES: permission denied
```

**Cause:** The file is owned by `root:root` (Claude's Edit tool, `cp`, or any editor running as root resets ownership). The container user `openclaw` (uid=999) can only read the file when owner is `sentinel` (also uid=999).

**Fix — always run after ANY edit to openclaw.json:**
```bash
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
chmod 640 /root/.openclaw/openclaw.json
ls -la /root/.openclaw/openclaw.json
# Expected: -rw-r----- 1 sentinel systemd-journal ...
```

Then reload:
```bash
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1
```

**Same rule applies to all files under `/root/.openclaw/`** — always chown after editing.

### Cron daily brief times out (`FailoverError: LLM request timed out`)

**Symptom:** `news-brief-state.json` shows `lastRunStatus: "error"`, `consecutiveErrors: N`, `lastError: "cron: job execution timed out"`. OpenClaw logs:
```
lane task error: lane=cron durationMs=60045 error="FailoverError: LLM request timed out."
```

**Cause:** `timeoutSeconds` in `jobs.json` is too short. Codex + Brave search typically takes 75-120s to complete a brief. The previous setting was `60` which is too tight. Current setting: 120s.

**Fix:**
```bash
cat /root/.openclaw/cron/jobs.json | python3 -m json.tool | grep timeoutSeconds
# Should be 120. If not:

python3 -c "
import json
with open('/root/.openclaw/cron/jobs.json') as f: d = json.load(f)
for job in d['jobs']:
    job['payload']['timeoutSeconds'] = 120
with open('/root/.openclaw/cron/jobs.json', 'w') as f: json.dump(d, f, indent=2)
print('set to 120')
"
```

> **Do not set above 120** — 180s was the original value but it caused zombie runs where `last_run.status` stayed `"running"` indefinitely.

### Channel commands not working (`@MangenkyoBot /ai_daily_brief status` produces no response)

This is a 3-layer problem. Check each layer in order:

**Layer 1 — Telegram bot privacy mode**

By default, Telegram bots only receive commands addressed by name in group chats. A message like `@MangenkyoBot /ai_daily_brief status` (mention then command) may never be delivered to the bot by Telegram.

Fix option A — Disable privacy mode (recommended for a dedicated supergroup):
```bash
# 1. Open Telegram → @BotFather → /setprivacy → select bot → Disable
# 2. Restart gateway to re-initialize polling:
cd /root/openclaw && docker compose restart openclaw-gateway
```
After this, plain `/ai_daily_brief status` works in the approved supergroup.

Fix option B — Keep privacy mode ON:
Users must use `/command@BotName` format:
```
/ai_daily_brief@MangenkyoBot status
/ai_daily_brief@MangenkyoBot top5 12h
```
The `@BotName` suffix is stripped automatically by the command normalizer before routing.

**Layer 2 — Supergroup chat ID not registered**

The bot ignores group messages unless the chat ID is in `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS`.

Discover the chat ID:
```bash
TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' /root/openclaw/.env | tail -n1 | cut -d= -f2-)"
curl -s "https://api.telegram.org/bot${TG_TOKEN}/getUpdates" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for u in (data.get('result') or []):
    msg = u.get('message') or u.get('channel_post') or u.get('my_chat_member') or {}
    chat = msg.get('chat', {})
    if chat.get('id'):
        print(f'chat_id={chat[\"id\"]}  type={chat.get(\"type\")}  title={chat.get(\"title\",\"\")}')
"
```
Register it:
```bash
cd /root/openclaw
sed -i '/^OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=/d' .env
echo 'OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=-1001234567890' >> .env  # replace with real ID
```

**Layer 3 — Rollout and verify**

```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Smoke test must pass:
- `Interactive Telegram chats registered for command invocation`
- `No active Telegram webhook (polling mode unblocked)`
- `Telegram ingest runtime is running`

If smoke test passes but channel commands still fail:
1. Confirm the bot is a member (or admin) of the supergroup.
2. Send a message in the supergroup first so `getUpdates` picks it up.
3. Check bot privacy mode via BotFather: `/mybots` → select bot → `Bot Settings` → `Group Privacy`.

**Layer 4 — Messages sent as channel / anonymous admin**

If users/admins post as channel identity, Telegram may omit `from.id`, which can break native command auth.

Enable interactive-chat compatibility mode:
```bash
cd /root/openclaw
sed -i '/^OPENCLAW_TELEGRAM_INTERACTIVE_ALLOW_ANY_SENDER=/d' .env
echo 'OPENCLAW_TELEGRAM_INTERACTIVE_ALLOW_ANY_SENDER=1' >> .env
sed -i '/^OPENCLAW_TELEGRAM_NATIVE_COMMANDS=/d' .env
echo 'OPENCLAW_TELEGRAM_NATIVE_COMMANDS=0' >> .env
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```
Result:
- approved interactive chat can invoke `/ai_daily_brief ...` via text command routing
- native Telegram command menu registration is intentionally disabled

### OpenClaw not responding to Telegram
```bash
# Verify container is running
docker ps

# Check if gateway is listening
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18789/__openclaw__/canvas/

# Check Telegram token is correct
docker compose logs openclaw-gateway | grep -i telegram

# Restart the container
docker compose restart openclaw-gateway
```

### Commands work sometimes and sometimes don't
This usually means one of these:
1. You're chatting with the wrong bot (Sentinel vs OpenClaw) or wrong username typo.
2. Deprecated alias skills (`/aibrief*`) still exist on runtime.
3. OpenClaw and Sentinel tokens are accidentally the same.

Verify OpenClaw bot identity:
```bash
grep '^OPENCLAW_TELEGRAM_TOKEN=' /root/openclaw/.env | cut -d= -f2- | \
  xargs -I{} curl -s "https://api.telegram.org/bot{}/getMe"
```
Confirm the returned username matches the bot chat you are testing in Telegram.

Validate quickly on VPS:
```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Then in Telegram:
- OpenClaw bot: `/ai_daily_brief status`
- OpenClaw compatibility alias: `/ai_daily_brief_status`
- Sentinel bot: `/status`

If OpenClaw replies with pairing:
```bash
docker exec openclaw-openclaw-gateway-1 node openclaw.mjs pairing list --channel telegram
docker exec openclaw-openclaw-gateway-1 node openclaw.mjs pairing approve telegram <PAIR_CODE>
```

### AI brief should post to channel but still lands in DM
Checks:
```bash
python3 -m json.tool /root/.openclaw/workspace/logs/news-brief-state.json | sed -n '1,120p'
```
Confirm:
- `config.output_channel` is set (e.g. `@dandailybriefAI`)
- DM invocation works by default.
- Channel/supergroup invocation requires `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` to include the chat ID.

Set/update it safely:
```bash
cd /root/openclaw-project
./infrastructure/set-aibrief-output-channel.sh @dandailybriefAI
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Telegram-side requirement:
- The OpenClaw bot must be added as admin in the target channel with permission to post messages.

If you also want to invoke commands from the channel/supergroup itself:
```bash
cd /root/openclaw
sed -i '/^OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=/d' .env
echo 'OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=-1003826801947' >> .env  # replace with your chat id
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
```

### Dashboard shows `gateway token missing` or `pairing required`
Symptoms in browser:
- `unauthorized: gateway token missing`
- `pairing required`

This is a Control UI auth flow issue (not Telegram ingest).

Use the `ocdash` script (or the manual steps below):
```bash
# Automatic: handles tunnel + URL + browser
bash infrastructure/ocdash.sh

# Or manually:
ssh -N -L 28789:127.0.0.1:18789 root@46.225.170.60   # terminal 1
RAW_URL="$(ssh openclaw 'docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs dashboard --no-open 2>/dev/null | sed -n "s/^Dashboard URL: //p" | head -n1')"
URL="${RAW_URL/127.0.0.1:18789/127.0.0.1:28789}"
open "$URL"                                             # terminal 2
```

If still blocked by `pairing required`, approve latest device request and refresh:
```bash
ssh root@YOUR_VPS_IP 'docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs devices approve --latest --json'
```

Quick log check:
```bash
ssh root@YOUR_VPS_IP "cd /root/openclaw && docker compose logs --since=90s openclaw-gateway | grep -Ei 'token_missing|pairing required|unauthorized|device token mismatch' || echo 'no auth errors'"
```

If command is ignored, verify command registration:
```bash
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
# either:
# - "Telegram native AI brief commands are registered ..."
# - or "Telegram native commands intentionally disabled (text-command routing mode)"
```

### `/ai_daily_brief` returns generic daily briefing content
This indicates command routing collision between AI brief and generic daily briefing.

```bash
# Re-sync latest config + skill files and restart services
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh

# Validate command path and state
./infrastructure/aibrief-smoke-test.sh
```

Then test in Telegram:
- `/ai_daily_brief status`
- `/ai_daily_brief top5`
- `/ai_daily_brief_top5` (compatibility alias)
- `/commands` (confirm `/ai_daily_brief` appears in listed commands)

If still wrong, inspect:
- `/root/.openclaw/workspace/AGENTS.md`
- `/root/.openclaw/workspace/SOUL.md`
- `/root/.openclaw/skills/news-brief/SKILL.md`

If `/root/.openclaw/workspace/AGENTS.md` or `/root/.openclaw/workspace/SOUL.md` is missing, the gateway falls back to default behavior and command routing becomes inconsistent. Re-run:
```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

### Telegram configured but not consuming commands (`running=false`)
If `aibrief-smoke-test.sh` reports:
- `Telegram running: False`
- `Telegram tokenSource: none`

then the gateway runtime is up but Telegram ingest is not active. Most common causes:
1. config ownership drift (`openclaw.json` not readable by runtime user)
2. token not loaded into runtime (`tokenSource=none`)
3. stale container with old env/config

Do this in order:
```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

If still failing, force config resync + recreate:
```bash
cd /root/openclaw-project
bash ./infrastructure/sync-openclaw-config.sh /root/openclaw/.env /root/openclaw-project/openclaw/openclaw-config.json
cd /root/openclaw
docker compose up -d --force-recreate
```

Important:
- run `docker compose ...` from `/root/openclaw` (or use `-f /root/openclaw/docker-compose.yml`).
- running compose commands from `/root/openclaw-project` will fail with `no configuration file provided`.
Then re-run:
```bash
cd /root/openclaw-project
./infrastructure/aibrief-smoke-test.sh
```

Required smoke-test lines:
- `Gateway runtime user can read /home/node/.openclaw/openclaw.json`
- `Runtime config has Telegram auth material (botToken/tokenFile) at channels.telegram(.accounts.default)`
- `Gateway container has Telegram bot token in environment` (warning is acceptable only if tokenSource is `config` and running is true)
- `Telegram ingest runtime is running`
- `Gateway Telegram token source is ...` (not `none`)

If smoke test reports a gateway token mismatch:
- remove duplicate `OPENCLAW_GATEWAY_TOKEN=` lines from `/root/openclaw/.env` (keep one canonical value)
- rerun rollout so runtime `gateway.auth.token` and `.env` are aligned

### Telegram webhook blocking polling mode
If `aibrief-smoke-test.sh` shows Telegram configured but `running=false`, an active webhook can be blocking long-polling (`getUpdates`).

Check webhook status:
```bash
TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' /root/openclaw/.env | tail -n1 | cut -d= -f2-)"
curl -s "https://api.telegram.org/bot${TG_TOKEN}/getWebhookInfo" | python3 -m json.tool
```

If `result.url` is non-empty, clear webhook and restart gateway:
```bash
curl -s "https://api.telegram.org/bot${TG_TOKEN}/deleteWebhook?drop_pending_updates=false"
cd /root/openclaw
docker compose restart openclaw-gateway
```

Rollout now attempts this automatically, but manual cleanup is still valid if the token was previously used by another Telegram integration.

### Telegram provider is running but commands are silently ignored
If `channels.status` shows Telegram `running=true` and `tokenSource` is valid, but `/ai_daily_brief*` commands still never trigger, check for a stale update-offset file.

Background:
- OpenClaw stores last processed Telegram `update_id` per account in:
  - `/root/.openclaw/telegram/update-offset-default.json`
- If that value becomes stale after token/account swaps, inbound updates can be skipped with no obvious runtime error.

Reset safely:
```bash
cd /root/openclaw-project
./infrastructure/reset-telegram-offset.sh default
```

Then validate:
```bash
cd /root/openclaw-project
./infrastructure/aibrief-smoke-test.sh
```

The smoke test now prints account runtime fields from `channels.status` (`accountId`, `running`, `tokenSource`, `lastInboundAt`, `lastOutboundAt`) and warns when offset state is a likely blocker.

Avoid `openclaw doctor --fix` as part of AI-brief rollout automation. It can rewrite config and interfere with explicit Telegram token wiring.

### AI brief returns "unknown error" and `last_run.status` stays `running`
Symptom:
- Telegram returns `An unknown error occurred` for `/ai_daily_brief_top5` or `/ai_daily_brief_evening`.
- `news-brief-state.json` shows `last_run.status="running"` long after the run should have ended.

Cause:
- The skill is prompt-driven and can be interrupted before finalize writes happen.
- This leaves a stale lock-like run state that can confuse subsequent invocations.

Fix:
```bash
cd /root/openclaw-project
./infrastructure/reconcile-ai-brief-state.sh /root/.openclaw/workspace/logs/news-brief-state.json
./infrastructure/aibrief-smoke-test.sh
```

Expected:
- reconcile script prints `RECOVERED run_id=...` when stale lock is found.
- smoke test passes `AI brief last_run is not stuck in running state (...)`.

Notes:
- `vps-rollout-aibrief.sh` now runs this reconcile step automatically.
- stale threshold defaults to 900s (override with `STALE_AFTER_SECONDS=...` if needed).

### `news-brief-state.json` is invalid JSON after cron timeout

**Symptom:** Any command that reads `news-brief-state.json` fails silently or with a parse error. Python validation shows:
```
json.decoder.JSONDecodeError: Expecting ',' delimiter: line NNN column 3
```

**Cause:** The cron job timed out mid-write. A partial flush left the `providers` block closed with `]` instead of `}`, producing:
```json
    "providers": {
        "brave_llm_context": { ... }
    ],   ← should be }
    "recent_story_fingerprints": ...
```

**Fix:**
```python
import json

path = '/root/.openclaw/workspace/logs/news-brief-state.json'
text = open(path).read()

# Fix the malformed closing brace
old = '    }\n  ],\n  "recent_story_fingerprints"'
new = '    }\n  },\n  "recent_story_fingerprints"'

if old in text:
    fixed = text.replace(old, new)
    json.loads(fixed)   # validate before saving
    open(path, 'w').write(fixed)
    print('Fixed OK')
else:
    print('Pattern not found — inspect file manually')
    # Try: python3 -m json.tool news-brief-state.json to find the error location
```

After fixing, run the reconcile script to clear any stale running lock:
```bash
bash /root/openclaw-project/infrastructure/reconcile-ai-brief-state.sh \
  /root/.openclaw/workspace/logs/news-brief-state.json
```

**Prevention:** Keep `timeoutSeconds` in `jobs.json` at `120` or above. If the brief is still timing out at 120s, raise to `150` — but do not go above `180` (causes zombie runs).

### Commands reach bot but AI brief never invokes (`last_run` stays null)
If `/ai_daily_brief*` returns generic replies and `last_run.run_id/mode/status` remain null, verify DM authorization:

`aibrief-smoke-test.sh` should show either:
- `Telegram DM allowFrom configured (...)`, or
- an intentional pairing setup you already approved.

Current behavior: smoke test now **fails** when it detects `dmPolicy=pairing` with empty `allowFrom`, because this blocks `/ai_daily_brief*` skill execution in DM until pairing is explicitly approved.

Fix with explicit allowlist (recommended):
```bash
cd /root/openclaw
sed -i '/^OPENCLAW_TELEGRAM_ALLOW_FROM=/d' .env
echo 'OPENCLAW_TELEGRAM_ALLOW_FROM=6182588021' >> .env   # replace with your Telegram user ID
sed -i '/^OPENCLAW_TELEGRAM_DM_POLICY=/d' .env
echo 'OPENCLAW_TELEGRAM_DM_POLICY=allowlist' >> .env

cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

The config sync also accepts fallback from `SENTINEL_ALLOWED_USERS` when `OPENCLAW_TELEGRAM_ALLOW_FROM` is not set.

### Commands are registered, inbound is healthy, but mode routes wrong
If Telegram ingest is healthy (`running=true`, `tokenSource!=none`) but command behavior is inconsistent (for example, `/ai_daily_brief_status` behaving like canonical `/ai_daily_brief`), check for duplicate trigger ownership across skills.

Why this matters:
- Native command routing should map each `/ai_daily_brief*` command to exactly one skill.
- If multiple skills declare the same trigger, runtime selection can become non-deterministic and force the wrong model/path.

Validate with smoke test:
- `AI brief slash triggers are uniquely mapped (no ambiguous duplicate trigger owners)`

If this line fails, align trigger ownership so each command has one owner:
- canonical skill owns only `/ai_daily_brief`
- alias skills own `/ai_daily_brief_morning|evening|top5|builder|watchlist|status`

Then rerun:
```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

### Gateway crash-loop after OpenClaw update: `non-loopback Control UI requires gateway.controlUi...`
Symptom:
- `openclaw-gateway` keeps restarting.
- Logs show: `non-loopback Control UI requires gateway.controlUi.allowedOrigins ...`

Cause:
- Newer OpenClaw builds require explicit `gateway.controlUi` policy when bind is non-loopback (`lan`/`0.0.0.0`).
- Runtime config was generated without `gateway.controlUi`.

Fix:
```bash
cd /root/openclaw-project
# ensure latest helper is installed
install -m 755 infrastructure/sync-openclaw-config.sh /usr/local/sbin/sync-openclaw-config.sh

# optional explicit origin allowlist (recommended when you know your hostnames)
# echo 'OPENCLAW_CONTROL_UI_ALLOWED_ORIGINS=http://46.225.170.60:18789' >> /root/openclaw/.env

/usr/local/sbin/sync-openclaw-config.sh /root/openclaw/.env /root/openclaw-project/openclaw/openclaw-config.json
cd /root/openclaw
docker compose up -d --force-recreate openclaw-gateway
```

Expected:
- `/root/.openclaw/openclaw.json` contains `gateway.controlUi`.
- Container health transitions to `healthy`.

### AI Brief commands still narrate or route inconsistently despite healthy ingest
Symptom:
- replies include process narration (`Reasoning:`, `I will now...`), or alias commands route to wrong behavior.

Cause:
- stale runtime skill folders (`daily-brief*`, `aibrief*`) can coexist with canonical `ai-daily-brief*`, creating trigger collisions.

Fix:
```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Expected smoke-test line:
- `No deprecated/conflicting alias skill folders on runtime`

### `/ai_daily_brief*` reports sub-agent/pairing block despite healthy Telegram ingest
Symptom:
- Telegram command is received and bot replies, but message says sub-agent spawn is blocked by pairing.
- `channels.status` still shows Telegram account `running=true`.

Cause:
- AI brief command flow was being treated as a strict sub-agent delegation path.
- If sub-agent spawn is unavailable, command can fail before skill execution even though channel ingest is healthy.

Fix:
- Ensure runtime SOUL/AGENTS config includes direct in-lane execution for `/ai_daily_brief*` commands.
- Roll out latest config, then restart gateway:

```bash
cd /root/openclaw-project
git fetch origin
git checkout main
git reset --hard origin/main
./infrastructure/vps-rollout-aibrief.sh
cd /root/openclaw
docker compose restart openclaw-gateway
```

Validation after rollout:
- `aibrief-smoke-test.sh` must pass:
  - `SOUL policy enforces direct in-lane execution for /ai_daily_brief*`
  - `AGENTS policy confirms /ai_daily_brief* does not require sub-agent spawn`

### AI Daily Brief has no outputs yet
No files under `/root/.openclaw/workspace/outputs/summaries/ai-brief-*.md` means no successful run yet.

Checks:
```bash
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
python3 -m json.tool /root/.openclaw/workspace/logs/news-brief-state.json | sed -n '1,120p'
```

Run manually from Telegram:
- `/ai_daily_brief morning` or `/ai_daily_brief evening`

### `/ai_daily_brief` says provider is unconfigured
This means Brave LLM Context grounding is not available to the runtime.

```bash
# 1) Set Brave key
nano /root/openclaw/.env
# add/update: BRAVE_API_KEY=...

# 2) Re-sync + restart OpenClaw
/usr/local/sbin/sync-openclaw-config.sh
cd /root/openclaw && docker compose up -d --force-recreate

# 3) Verify provider health
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
```

Expected smoke-test pass line:
- `Brave LLM Context API reachable (...)`

If smoke test shows LLM Context probe failing:
- check key length in failure output (`key_len=...`)
- rotate/re-paste `BRAVE_API_KEY` (no quotes, no trailing spaces/comments)
- ensure OpenClaw container sees the key:
```bash
docker exec openclaw-openclaw-gateway-1 sh -lc 'echo ${#BRAVE_API_KEY}'
```

AI brief is now configured for Brave LLM Context only. If LLM Context is unavailable, brief generation must fail fast with provider diagnostics (no fallback to `/res/v1/web/search`).

If smoke test reports `BRAVE_API_KEY appears invalid (len=...)`, the key format itself is wrong (commonly a truncated value like length 4). Replace it before debugging anything else.

### `/ai_daily_brief top5` is too slow
Symptoms:
- long "pipeline progress" replies instead of final brief
- repeated broad searches and high latency per run

Fast fix (keep Gemini Pro + Brave LLM Context):

```bash
cd /root/openclaw-project
git fetch origin
git checkout main
git reset --hard origin/main
./infrastructure/vps-rollout-aibrief.sh
```

This rollout now migrates legacy high-latency Brave defaults in state to optimized values:
- `count=14`, `maximum_number_of_urls=14`, `maximum_number_of_tokens=6144`
- `maximum_number_of_snippets=30`, `maximum_number_of_tokens_per_url=2048`, `maximum_number_of_snippets_per_url=20`
- performance defaults: `timeout_seconds=22`, `max_retries=1`, `backoff_seconds=[1,2]`
- method/filters defaults: `request_method=POST`, mode thresholds (`top5=strict`, `full=balanced`)
- optional controls: `goggles` (source re-ranking), `enable_local` (leave null for global AI news)

Verify active runtime state:

```bash
python3 - <<'PY'
import json
p='/root/.openclaw/workspace/logs/news-brief-state.json'
with open(p) as f:d=json.load(f)
cfg=(d.get('config') or {}).get('brave_llm_context') or {}
perf=(d.get('config') or {}).get('performance') or {}
print(cfg)
print(perf)
PY
```

Expected behavior after tuning:
- Top5 runs target `<45s` and avoid verbose stage-by-stage narration.
- First Brave query runs always; second query runs only when coverage is weak.
- Model stays on `google/gemini-2.5-pro` for AI Daily Brief synthesis.
- Brave calls respect a 1-second inter-call delay to avoid burst-rate issues.

If verbose narration still appears (for example `Reasoning:` blocks or "I will now..." messages), clear stale runtime sessions and restart the gateway:

```bash
cd /root/openclaw-project
./infrastructure/reset-openclaw-telegram-sessions.sh
```

Then retest from Telegram with:
- `/ai_daily_brief_status`
- `/ai_daily_brief_top5`

If `/reset` still emits `Reasoning:` preamble after session reset, confirm runtime defaults in `/root/.openclaw/openclaw.json`:

```bash
python3 - <<'PY'
import json
with open('/root/.openclaw/openclaw.json') as f:
    d=json.load(f)
defaults=((d.get('agents') or {}).get('defaults') or {})
print('thinkingDefault=', defaults.get('thinkingDefault'))
print('verboseDefault=', defaults.get('verboseDefault'))
PY
```

Expected:
- `thinkingDefault=off`
- `verboseDefault=off`

### Gemini routing and fallback checks

If the default Gemini path is not working as expected:

```bash
# Verify key is present in .env (non-empty)
grep '^GEMINI_API_KEY=' /root/openclaw/.env

# Verify key is injected into container env
docker exec openclaw-openclaw-gateway-1 sh -lc 'echo ${#GEMINI_API_KEY}'

# Check model/provider traces
cd /root/openclaw
docker compose logs --since=120s openclaw-gateway | grep -Ei 'gemini|google|model|fallback|529|overload'
```

Expected behavior:
- `GEMINI_API_KEY` is retained for optional manual fallback paths, not the primary runtime.
- OpenClaw keeps `openai-codex/gpt-5.3-codex` as primary and `google/gemini-2.5-flash` as fallback.
- Sentinel primary runtime is `openai/gpt-5-codex`; for manual rollback, set `SENTINEL_PROVIDER=google` and `SENTINEL_MODEL=gemini-2.5-flash`.

Claude-only mode (intentional temporary rollback):
```bash
cd /root/openclaw
sed -i '/^GEMINI_API_KEY=/d' .env
echo 'GEMINI_API_KEY=' >> .env
/usr/local/sbin/sync-openclaw-config.sh
docker compose up -d --force-recreate
```

### High token usage
1. Check provider usage dashboards (Codex primary for OpenClaw heartbeat/chat; Sentinel on OpenAI Codex API) for daily breakdown
2. Verify AGENTS.md keeps Codex as default and heartbeat stays on the lightweight heartbeat policy
3. Check if heartbeat is running during silent hours (it shouldn't)
4. Review conversation logs for unnecessary Gemini Pro/Sonnet/Opus escalations
5. Ensure compaction mode is "safeguard" in openclaw.json
6. Verify contextTokens is 65536 (not 131K or 1M) — check both gateway defaults AND per-session overrides:
```bash
python3 -c "
import json
with open('/root/.openclaw/agents/main/sessions/sessions.json') as f:
    d = json.load(f)
for sid, sess in d.items():
    ct = (sess.get('config') or {}).get('contextTokens', 'default')
    print(f'{sid}: contextTokens={ct}')
"
```
7. Verify contextPruning is enabled:
```bash
python3 -c "
import json
with open('/root/.openclaw/openclaw.json') as f: d = json.load(f)
print(d['agents']['defaults'].get('contextPruning', 'NOT SET'))
"
# Expected: {'mode': 'cache-ttl', 'ttl': '30m', 'keepLastAssistants': 3, 'minPrunableToolChars': 50000}
```
8. Check for duplicate workspace files (e.g., AGENTS.md in both root and workspace) — each duplicate adds ~3,700 tokens per call

### API cost tracking file missing or stale
Sentinel now writes API usage/cost events continuously and the rollout script builds a unified rollup.

Regenerate and inspect:
```bash
cd /root/openclaw-project
./infrastructure/update-api-cost-rollup.sh \
  /root/.openclaw/workspace/logs/news-brief-state.json \
  /var/log/sentinel/api-cost-summary.json \
  /root/.openclaw/workspace/logs/api-cost-rollup.json

python3 -m json.tool /root/.openclaw/workspace/logs/api-cost-rollup.json | sed -n '1,160p'
```

Expected files:
- `/var/log/sentinel/api-usage.jsonl` (append-only events)
- `/var/log/sentinel/api-cost-summary.json` (Sentinel daily/weekly/monthly aggregates)
- `/root/.openclaw/workspace/logs/api-cost-rollup.json` (combined AI Brief + Sentinel totals)

## Expert Network Brief Issues

### `/expert_network_brief` or `/brief` not responding or routing wrong
```bash
# Verify news-brief skill exists on runtime (V4 — single skill for all brief commands)
ls -la /root/.openclaw/skills/news-brief/SKILL.md

# Verify state file
python3 -m json.tool /root/.openclaw/workspace/logs/news-brief-state.json

# Check ownership
ls -la /root/.openclaw/skills/news-brief/SKILL.md
# Expected: sentinel:systemd-journal

# Re-sync from repo if needed
rsync -av /root/openclaw-project/openclaw/skills/ /root/.openclaw/skills/
chown -R sentinel:systemd-journal /root/.openclaw/skills/
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1
```

### ENB cron not running
```bash
# Check cron jobs
python3 -c "
import json
with open('/root/.openclaw/cron/jobs.json') as f: d = json.load(f)
for j in d['jobs']:
    print(f\"{j['name']}: enabled={j['enabled']}, schedule={j['schedule']['expr']}, model={j['payload']['model']}\")
"
# Expected: 3 jobs (AI Brief + ENB Morning + ENB Evening)

# Check for recent ENB runs
python3 -c "
import json
with open('/root/.openclaw/workspace/logs/news-brief-state.json') as f: d = json.load(f)
print('last_run:', d.get('last_run'))
print('history count:', len(d.get('history', [])))
"
```

### ENB state file missing or corrupted
```bash
# Re-create initial state
python3 -c "
import json
state = {
    'schema_version': '2026-02-27-v1',
    'config': {
        'competitors': ['GLG', 'AlphaSights', 'Guidepoint', 'Third Bridge', 'Capvision', 'Coleman Research', 'Atheneum Partners', 'Prospex'],
        'output_channel': '-1003826801947',
        'focus_areas': ['AI capabilities', 'product launches', 'strategic moves', 'market expansion']
    },
    'last_run': None,
    'history': [],
    'recent_story_fingerprints': []
}
with open('/root/.openclaw/workspace/logs/news-brief-state.json', 'w') as f:
    json.dump(state, f, indent=2)
print('Created OK')
"
chown sentinel:systemd-journal /root/.openclaw/workspace/logs/news-brief-state.json
```

### OpenClaw out of memory (OOM killed)
```bash
# Check if container was OOM killed
docker inspect openclaw-openclaw-gateway-1 | grep -i oom

# Reduce memory limit if needed, or check for memory leaks
# Current limit: 2560MB in docker-compose.yml
# On CPX22 (4GB total), this leaves ~1.5GB for Sentinel + OS
```

## Job Radar Issues

### `/job_radar` is slow or API costs are high
Enforce the production tuning profile:
```bash
cd /root/job-radar
set_kv(){ key="$1"; val="$2"; if grep -q "^${key}=" .env; then sed -i "s|^${key}=.*|${key}=${val}|" .env; else printf "%s=%s\n" "$key" "$val" >> .env; fi; }
set_kv JOB_SEARCH_BRAVE_ONLY false
set_kv BRAVE_RESULTS_PER_QUERY 8
set_kv BRAVE_CONTEXT_MAX_TOKENS 3072
set_kv BRAVE_CONTEXT_MAX_SNIPPETS 20
set_kv BRAVE_CONTEXT_THRESHOLD_MODE strict
set_kv BRAVE_DISCOVERY_TARGET_JOBS 24
set_kv JOB_MAX_AGE_DAYS 45
set_kv HEALTH_LOG_INTERVAL_MINUTES 180
set_kv HEALTH_EXTERNAL_CHECK_TTL_SECONDS 10800
docker compose -f docker-compose.job-radar.yml up -d --build job-radar-api
```

Verify:
```bash
curl -sS http://127.0.0.1:8080/health/full | python3 -m json.tool | sed -n '1,120p'
curl -sS -X POST http://127.0.0.1:8080/api/v1/ingestion/sync
sleep 6
docker compose -f docker-compose.job-radar.yml logs --tail=220 job-radar-api | \
  grep -E 'pipeline.start|connectors|target_reached|stale_filtered|llm/context'
```

Expected:
- `brave_only: true`
- `connectors: ["brave_discovery"]`
- `target_reached` and `stale_filtered` counters present.

### Job feed contains noisy aggregator links or stale listings
Purge non-ATS and stale rows from the database:
```bash
cd /root/job-radar
DBPW="$(grep '^JOB_RADAR_DB_PASSWORD=' .env | cut -d= -f2-)"
cat >/tmp/job-radar-clean.sql <<'SQL'
BEGIN;
WITH stale AS (
  SELECT id FROM jobs_normalized
  WHERE posted_at IS NOT NULL
    AND posted_at < (NOW() - INTERVAL '45 days')
), noisy AS (
  SELECT id FROM jobs_normalized
  WHERE canonical_url !~* 'greenhouse\\.io|lever\\.co|workable\\.com'
), target AS (
  SELECT id FROM stale
  UNION
  SELECT id FROM noisy
)
DELETE FROM job_events je USING target t WHERE je.job_id = t.id;
DELETE FROM job_scores js USING target t WHERE js.job_id = t.id;
DELETE FROM jobs_normalized jn USING target t WHERE jn.id = t.id;
DELETE FROM jobs_raw jr WHERE NOT EXISTS (SELECT 1 FROM jobs_normalized jn WHERE jn.job_raw_id = jr.id);
COMMIT;
SQL
docker exec -i -e PGPASSWORD="$DBPW" job-radar-db psql -U jobradar -d jobradar < /tmp/job-radar-clean.sql
curl -sS "http://127.0.0.1:8080/api/v1/jobs?limit=5" | python3 -m json.tool
```

### `/job_health` is repeatedly calling external APIs
`/health/full` now caches external checks for `HEALTH_EXTERNAL_CHECK_TTL_SECONDS` (default 10800s = 3 hours).
If you still see high call volume:
1. verify `HEALTH_EXTERNAL_CHECK_TTL_SECONDS=10800` is set in `/root/job-radar/.env`
2. restart API container
3. call `/health/full` twice quickly; second response should include `"cached": true` on external checks.

### Health checks burning API credits
**Symptom:** Brave or Anthropic usage appears in logs/dashboards from health checks.

**Cause (fixed 2026-02-27):** Health checks previously used real LLM endpoints:
- Brave: sent LLM Context query (`/res/v1/llm/context`) every 3h
- Anthropic: sent a real completion every 3h (previously used Haiku — now banned)

**Current behavior (zero-cost):**
- Brave: uses cheap web search endpoint (`/res/v1/web/search` with count=1) — no LLM cost
- Anthropic: uses empty-messages validation (sends empty messages array → 400 = key valid, 401 = key invalid) — zero tokens

If you see the old behavior, rebuild the API container:
```bash
cd /root/job-radar && docker compose -f docker-compose.job-radar.yml build job-radar-api
docker compose -f /root/openclaw/docker-compose.yml -f /root/job-radar/docker-compose.job-radar.yml --project-directory /root/job-radar up -d job-radar-api
```

### Job Radar using expensive Pro model
**Symptom:** LLM calls from Job Radar use `google/gemini-2.5-pro` instead of Flash.

**Cause:** `llm_standard_model` in `config.py` defaulted to Pro.

**Fix (applied 2026-02-27):** Default changed to `google/gemini-2.5-flash`. Verify:
```bash
docker exec job-radar-api python3 -c "from app.config import settings; print(settings.llm_standard_model)"
# Expected: google/gemini-2.5-flash
```

### Digest sends same jobs repeatedly (dedup broken)
**Symptom:** Same 5 jobs appear in every digest, even though dedup should prevent re-sending.

**Cause:** Digest hash included timestamp in the formatted message, producing a different hash each run.

**Fix (applied 2026-02-27):** Hash is now content-based: `f"{digest_type}:" + ",".join(j["id"] for j in jobs)`. Rebuild API container if still seeing old behavior.

## Sentinel Issues

### Sentinel files have wrong ownership (won't start or breaks on restart)

**Symptom:** Sentinel starts but immediately fails with permission errors, OR Python imports fail.

**Cause:** After copying or editing any `.py` file in `/opt/sentinel/` as root, ownership resets to `root:root`. The `sentinel` user (uid=999) can't read them.

**Fix — always run after copying/editing sentinel Python files:**
```bash
chown sentinel:sentinel /opt/sentinel/*.py
ls -la /opt/sentinel/*.py
# Expected: -rw-r--r-- 1 sentinel sentinel ...
systemctl restart sentinel
journalctl -u sentinel -n 20 --no-pager
```

### Sentinel startup shows `FutureWarning: google.generativeai deprecated`

**Symptom:** Every Sentinel startup logs:
```
FutureWarning: All support for the `google.generativeai` package has ended.
Please switch to the `google.genai` package as soon as possible.
```

**Cause:** `sentinel.py` still imports `google.generativeai` (the old SDK). This is a **non-critical warning** — Sentinel still works correctly. The migration to `google.genai` requires updating the import pattern and API calls in `sentinel.py`.

**Immediate workaround:** None needed — Gemini still responds normally.

**Permanent fix (future work):** Migrate `sentinel/sentinel.py` to use `google.genai` instead of `google.generativeai`. The Google AI Python SDK README has a migration guide.

### Sentinel won't start
```bash
# Check service status
systemctl status sentinel

# View logs
journalctl -u sentinel -n 50

# Common causes:
# 1. Missing env vars — check /root/openclaw/.env, then sync to /etc/sentinel/sentinel.env
# 2. Python venv broken — recreate: python3 -m venv /opt/sentinel/venv
# 3. Dependencies missing — reinstall: /opt/sentinel/venv/bin/pip install -r requirements.txt
# 4. If .env was edited, run: /usr/local/sbin/sync-sentinel-env.sh
```

### Sentinel command blocked
The tool whitelist is intentionally strict. If a legitimate command is blocked:
1. Check validator functions in `tools.py` (`is_command_allowed` and `_validate_*`)
2. Add or adjust a validator for the command shape if it's safe
3. Restart Sentinel: `systemctl restart sentinel`

### Sentinel Telegram bot not responding
```bash
# Check if the process is running
systemctl is-active sentinel

# Check for Python errors
journalctl -u sentinel --since "1 hour ago" | grep -i error

# Verify Telegram token
grep SENTINEL_TELEGRAM_TOKEN /root/openclaw/.env 2>/dev/null || echo "Check environment variables"
```

### Sentinel says OpenAI returned empty response
This is usually a transient Responses API/provider edge case.

```bash
# 1) Confirm Sentinel is on the expected primary runtime
grep '^SENTINEL_PROVIDER=' /root/openclaw/.env
grep '^SENTINEL_MODEL=' /root/openclaw/.env

# 2) Sync runtime env + restart service
/usr/local/sbin/sync-sentinel-env.sh
systemctl restart sentinel

# 3) Inspect recent provider logs
journalctl -u sentinel -n 80 --no-pager | grep -Ei 'google|gemini|empty|fallback|error'
```

Expected behavior:
- Sentinel should remain on Gemini primary by default.
- If Gemini returns no usable text, Sentinel retries once and responds with a concise retry hint instead of silent failure.

### Sentinel token tracking shows 0 for all Gemini calls

**Symptom:** `/cost` or api-usage.jsonl shows `input_tokens=0, output_tokens=0` for every Gemini call, while Anthropic calls track correctly.

**Cause (fixed 2026-02-27):** `_extract_google_usage()` called `_coerce_mapping()` on Gemini proto objects, which fell through to the except clause returning a dict wrapper. Proto objects expose fields as attributes, NOT dict keys.

**Fix:** Uses direct `getattr()` on proto object attributes:
```python
input_tokens = int(getattr(usage_obj, "prompt_token_count", 0) or 0)
output_tokens = int(getattr(usage_obj, "candidates_token_count", 0) or 0)
```

If you see 0-token tracking, ensure `/opt/sentinel/sentinel.py` has the updated `_extract_google_usage` method, then restart:
```bash
cp /root/openclaw-project/sentinel/sentinel.py /opt/sentinel/sentinel.py
chown sentinel:sentinel /opt/sentinel/sentinel.py
systemctl restart sentinel
```

### Sentinel slash commands consuming tokens unnecessarily

**Symptom:** `/status`, `/openclaw`, `/security`, `/backup` each use ~1,940 tokens because they route through the LLM.

**Fix (applied 2026-02-27):** All slash commands now bypass the LLM entirely — they execute tools directly in Python and format results without any API call. The `/cost` command was also added (zero-cost).

Zero-cost commands: `/status`, `/openclaw`, `/security`, `/backup`, `/cost`
Static responses (no LLM): "hi", "hello", "thanks", "ok", "help", "ping"

### Sentinel footer (tokens/cost) missing in Telegram replies
Sentinel now appends a usage footer to every LLM-generated reply.

```bash
# Ensure COP conversion + token cap envs are present
grep '^SENTINEL_MAX_TOKENS=' /root/openclaw/.env
grep '^SENTINEL_USD_TO_COP_RATE=' /root/openclaw/.env

# Sync + restart after changes
/usr/local/sbin/sync-sentinel-env.sh
systemctl restart sentinel
```

Footer format:
- `Tokens used: <in>/<out> - USD $<cost> / COP $<cost>`
- `- Brave api: <n>` appears only when Brave was used in that request.

## Infrastructure Issues

### SSH tunnel disconnects
Add to your Mac's `~/.ssh/config`:
```
ServerAliveInterval 60
ServerAliveCountMax 3
```

Or use autossh for persistent tunnels:
```bash
brew install autossh
autossh -M 0 -N openclaw
```

### Disk space running low
```bash
# Check disk usage
df -h /

# Check Docker build cache (can grow to 37GB+)
docker system df

# Clean Docker build cache (biggest space saver)
docker builder prune --all --force

# Clean other Docker resources
docker system prune -f

# Check backup size
du -sh /root/backups/

# Remove old backups manually if needed
ls -lth /root/backups/

# Check journald size
journalctl --disk-usage
```

**Prevention:** A weekly Docker prune cron job runs automatically (added 2026-02-27):
```bash
# Verify cron is set up
crontab -l | grep docker
# Expected: 0 4 * * 0 docker builder prune --all --force > /dev/null 2>&1
```

**Journald is capped** at 100MB (`SystemMaxUse=100M` in `/etc/systemd/journald.conf`).

**Sentinel logs** are rotated weekly via `/etc/logrotate.d/sentinel` (12 rotations for .jsonl, 4 for .log).

### UFW blocking legitimate traffic
```bash
# Check current rules
ufw status verbose

# The only inbound rule should be SSH (22/tcp)
# OpenClaw is accessed via SSH tunnel, not direct connection
# If you need to add a rule temporarily:
ufw allow from YOUR_IP to any port 18789
```

### fail2ban blocked your IP
```bash
# Check banned IPs
fail2ban-client status sshd

# Unban your IP
fail2ban-client set sshd unbanip YOUR_IP
```

## Recovery Procedures

### Restore from backup
```bash
chmod +x /root/openclaw-project/infrastructure/restore.sh
./restore.sh /root/backups/openclaw-YYYYMMDD_HHMMSS.tar.gz
```

### Full system rebuild
If the VPS is compromised or corrupted:
1. Destroy the VPS in Hetzner Console
2. Create a new CPX22 with the same SSH key
3. Re-run the deployment from Step 3 in DEPLOYMENT.md
4. Restore from the latest backup

---

## GitHub / Repo Sync Procedures

### VPS is behind GitHub (Codex or direct edits on GitHub)

Situation: GitHub `main` has commits that aren't on the VPS yet.

```bash
cd /root/openclaw-project

# Check how far behind
git fetch origin
git log --oneline HEAD..origin/main

# Pull (stash local VPS-only files first if any)
git stash --include-untracked
git pull --rebase origin main
git stash drop   # drop stash — don't pop (stash may be old versions pre-GitHub changes)

# Deploy sentinel files to running service
cp sentinel/sentinel.py sentinel/telegram_handler.py sentinel/config.py sentinel/cost_tracker.py /opt/sentinel/
chown sentinel:sentinel /opt/sentinel/*.py

# Sync openclaw skills and config docs
rsync -av openclaw/skills/ /root/.openclaw/skills/
cp openclaw/config/AGENTS.md /root/.openclaw/AGENTS.md
cp openclaw/config/SOUL.md /root/.openclaw/SOUL.md
cp openclaw/config/MEMORY.md /root/.openclaw/MEMORY.md

# Restart sentinel to pick up new code
systemctl restart sentinel
sleep 3
systemctl is-active sentinel

# Reload OpenClaw config
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1
sleep 3
docker logs openclaw-openclaw-gateway-1 --since 5s 2>&1 | grep -i "invalid\|error"
```

### Pushing VPS changes to GitHub

No SSH key or credential helper is configured on the VPS. Use a GitHub PAT:

```bash
cd /root/openclaw-project

# Stage and commit
git add -p          # review changes interactively, or:
git add <specific-files>
git commit -m "your message"

# Push with PAT (replace TOKEN with your GitHub PAT)
git remote set-url origin "https://TOKEN@github.com/zsoist/cldw_Setup.git"
git push origin main
git remote set-url origin "https://github.com/zsoist/cldw_Setup.git"   # remove token from URL
```

> The PAT needs `repo` scope. Generate at GitHub → Settings → Developer Settings → Personal access tokens.

### openclaw.json has secrets — what goes in the repo?

The repo tracks `openclaw/openclaw-config.json` (template with `REPLACE_WITH_*` placeholders). The running file `/root/.openclaw/openclaw.json` has real tokens and is **not tracked** (it's outside the repo tree).

When making structural changes to `openclaw.json`, always mirror them to the template:
```bash
# Edit the running config
nano /root/.openclaw/openclaw.json
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
chmod 640 /root/.openclaw/openclaw.json

# Mirror structural changes (not secrets) to the template
nano /root/openclaw-project/openclaw/openclaw-config.json

# Validate template
python3 -m json.tool /root/openclaw-project/openclaw/openclaw-config.json > /dev/null && echo "OK"

# Commit template
cd /root/openclaw-project
git add openclaw/openclaw-config.json
git commit -m "update openclaw config template"
```

### After any `git pull` — ownership checklist

```bash
# 1. Sentinel Python files
chown sentinel:sentinel /opt/sentinel/*.py

# 2. openclaw.json (if you just edited it)
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
chmod 640 /root/.openclaw/openclaw.json

# 3. Restart services to pick up changes
systemctl restart sentinel
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1

# 4. Verify
systemctl is-active sentinel
docker logs openclaw-openclaw-gateway-1 --since 10s 2>&1 | grep -i "invalid\|error"
```
