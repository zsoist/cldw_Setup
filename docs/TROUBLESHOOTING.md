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
1. You're chatting with the wrong bot (Sentinel vs OpenClaw).
2. Deprecated alias skills (`/aibrief*`) still exist on runtime.
3. OpenClaw and Sentinel tokens are accidentally the same.

Validate quickly on VPS:
```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Then in Telegram:
- OpenClaw bot: `/ai_daily_brief status`
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
- `/commands` (confirm `/ai_daily_brief` appears in listed commands)

If still wrong, inspect:
- `/root/.openclaw/AGENTS.md`
- `/root/.openclaw/skills/ai-daily-brief/SKILL.md`
- `/root/.openclaw/skills/daily-briefing/SKILL.md`

### AI Daily Brief has no outputs yet
No files under `/root/.openclaw/workspace/outputs/summaries/ai-brief-*.md` means no successful run yet.

Checks:
```bash
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
python3 -m json.tool /root/.openclaw/workspace/logs/ai-brief-state.json | sed -n '1,120p'
```

Run manually from Telegram:
- `/ai_daily_brief morning` or `/ai_daily_brief evening`

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
