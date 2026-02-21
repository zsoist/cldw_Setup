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
