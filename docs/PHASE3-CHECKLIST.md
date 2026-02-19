# Phase 3: Go-Live Checklist

## Before starting (on your Mac)
- [ ] Hetzner CPX22 provisioned with Ubuntu 24.04
- [ ] SSH key added to VPS
- [ ] Can SSH into VPS: `ssh root@YOUR_VPS_IP`
- [ ] Anthropic API key created with $5 spending limit set
- [ ] Two Telegram bots created via @BotFather:
  - [ ] Bot 1: OpenClaw assistant (name: your_claw_bot)
  - [ ] Bot 2: Sentinel sysadmin (name: your_sentinel_bot)
- [ ] Your Telegram user ID noted (get from @userinfobot)

## Deployment (on VPS)
- [ ] secure.sh ran successfully
- [ ] deploy.sh ran successfully
- [ ] .env filled with all real values
- [ ] Docker image built without errors

## Go live
- [ ] `docker compose up -d` — OpenClaw gateway starts
- [ ] `docker compose logs -f` — shows "listening on ws://0.0.0.0:18789"
- [ ] SSH tunnel active: `ssh openclaw`
- [ ] Browser: http://127.0.0.1:18789/ loads, token accepted
- [ ] Telegram: /start on OpenClaw bot -> pairing works
- [ ] Send test message: "What time is it?" -> bot responds
- [ ] `systemctl start sentinel` — Sentinel starts
- [ ] Telegram: /status on Sentinel bot -> system stats returned

## Verification (budget: ~$2-5 API cost)
- [ ] OpenClaw: "Create a task: test task tracker" -> skill works
- [ ] OpenClaw: "What's the weather in Bogota?" -> web search works
- [ ] Sentinel: /security -> audit completes
- [ ] Sentinel: /openclaw -> health check passes
- [ ] Sentinel: /backup -> backup created

## Post-verification
- [ ] Raise Anthropic spending limit to $25/month
- [ ] Set up backup cron: `crontab -e` -> `0 3 * * * /root/openclaw-project/infrastructure/backup.sh`
- [ ] Monitor first 24h of API usage on console.anthropic.com
