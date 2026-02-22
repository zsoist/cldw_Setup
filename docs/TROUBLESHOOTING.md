# Troubleshooting Guide

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
python3 -m json.tool /root/.openclaw/workspace/logs/ai-brief-state.json | sed -n '1,120p'
```
Confirm:
- `config.output_channel` is set (e.g. `@dandailybriefAI`)
- Trigger command is sent in **DM with OpenClaw bot**, not in the channel

Set/update it safely:
```bash
cd /root/openclaw-project
./infrastructure/set-aibrief-output-channel.sh @dandailybriefAI
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Telegram-side requirement:
- The OpenClaw bot must be added as admin in the target channel with permission to post messages.

If command is ignored, verify command registration:
```bash
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
# must pass: "Telegram native command /ai_daily_brief is registered"
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
- `/root/.openclaw/skills/ai-daily-brief/SKILL.md`
- `/root/.openclaw/skills/daily-briefing/SKILL.md`

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

### AI Daily Brief has no outputs yet
No files under `/root/.openclaw/workspace/outputs/summaries/ai-brief-*.md` means no successful run yet.

Checks:
```bash
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
python3 -m json.tool /root/.openclaw/workspace/logs/ai-brief-state.json | sed -n '1,120p'
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

If smoke test shows:
- `Brave LLM Context probe failed (HTTP 422)` and
- `Brave Web Search is reachable`

then your Brave key is valid but likely does not include LLM Context entitlement.  
In this case AI brief can still run with fallback web-search grounding (partial mode).

If smoke test shows both probes failing (LLM Context + Web Search):
- check key length in failure output (`key_len=...`)
- rotate/re-paste `BRAVE_API_KEY` (no quotes, no trailing spaces/comments)
- ensure OpenClaw container sees the key:
```bash
docker exec openclaw-openclaw-gateway-1 sh -lc 'echo ${#BRAVE_API_KEY}'
```

If smoke test reports `BRAVE_API_KEY appears invalid (len=...)`, the key format itself is wrong (commonly a truncated value like length 4). Replace it before debugging anything else.

### High token usage
1. Check console.anthropic.com -> Usage for daily breakdown
2. Verify AGENTS.md has Haiku as default (not Sonnet)
3. Check if heartbeat is running during silent hours (it shouldn't)
4. Review conversation logs for unnecessary Sonnet/Opus escalations
5. Ensure compaction mode is "safeguard" in openclaw-config.json

### OpenClaw out of memory (OOM killed)
```bash
# Check if container was OOM killed
docker inspect openclaw-openclaw-gateway-1 | grep -i oom

# Reduce memory limit if needed, or check for memory leaks
# Current limit: 2560MB in docker-compose.yml
# On CPX22 (4GB total), this leaves ~1.5GB for Sentinel + OS
```

## Sentinel Issues

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

# Clean Docker resources
docker system prune -f

# Check backup size
du -sh /root/backups/

# Remove old backups manually if needed
ls -lth /root/backups/
```

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
