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
- [ ] deploy.sh ran successfully (all 9 steps completed)
- [ ] .env filled with all real values
- [ ] Docker image built without errors
- [ ] Verify file counts deployed:
  - [ ] 12 config files in /root/.openclaw/
  - [ ] 5 work agent files in /root/.openclaw/agents/work/
  - [ ] openclaw-config.json present
  - [ ] workspace directories created (personal/, business/, outputs/, logs/)

## Go live
- [ ] `docker compose up -d` — OpenClaw gateway starts
- [ ] `docker compose logs -f` — shows "listening on ws://0.0.0.0:18789"
- [ ] SSH tunnel active: `ssh openclaw`
- [ ] Browser: tokenized dashboard URL opens via local `28789` tunnel and token is accepted
- [ ] Telegram: /start on OpenClaw bot -> pairing works
- [ ] Send test message: "What time is it?" -> bot responds
- [ ] `systemctl start sentinel` — Sentinel starts
- [ ] Telegram: /status on Sentinel bot -> system stats returned

## Verification — Main Agent (budget: ~$2-5 API cost)
- [ ] "Create a task: test task tracker" -> skill works
- [ ] "What's the weather in Bogota?" -> web search works
- [ ] "What are my top 3 priorities?" -> reads personal/goals.md
- [ ] Wait for first heartbeat cycle (~55 min) -> stays silent if nothing actionable

## Verification — Work Agent
- [ ] Switch to work agent context
- [ ] "What are my current OKRs?" -> reads business/goals-okrs.md
- [ ] "Draft a follow-up email for a Dialectica project" -> professional tone
- [ ] Confirm work agent cannot access personal/ workspace files

## Verification — Sentinel
- [ ] /security -> audit completes
- [ ] /openclaw -> health check passes
- [ ] /backup -> backup created (check /var/backups/openclaw/)
- [ ] Verify backup excludes .env/.pem/.key files

## Verification — Cron Jobs
- [ ] Verify AI top stories brief fires at 06:00 COT (previous day scope)
- [ ] Confirm cron results append to workspace/logs/cron-job-results.md

## Post-verification
- [ ] Raise Anthropic spending limit to $25/month
- [ ] Set up backup cron: `crontab -e` -> `0 3 * * * /root/openclaw-project/infrastructure/backup.sh`
- [ ] Run health-check.sh: all checks pass
- [ ] Monitor first 24h of API usage on console.anthropic.com
- [ ] Review first daily brief and EOD log for quality
