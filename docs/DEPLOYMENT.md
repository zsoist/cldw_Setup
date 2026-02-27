# Deployment Guide

Step-by-step guide for deploying OpenClaw + Sentinel on a Hetzner CPX22 VPS.

## Prerequisites

- Hetzner Cloud account
- SSH key pair generated (`ssh-keygen -t ed25519`)
- Anthropic API key from console.anthropic.com
- Gemini API key from Google AI Studio / Google Cloud
- Brave Search API key from https://api.search.brave.com
- Two Telegram bots created via @BotFather
- Your Telegram user ID (get from @userinfobot)

## Step 1: Provision the VPS

1. Log into Hetzner Cloud Console
2. Create a new server:
   - **Image:** Ubuntu 24.04
   - **Type:** CPX22 (3 vCPU AMD, 4GB RAM, 80GB NVMe)
   - **Location:** Falkenstein or Nuremberg (EU) for lowest latency to Bogota
   - **SSH Key:** Add your public key
   - **Name:** `openclaw-vps`
3. Note the IP address

## Step 2: Configure SSH on your Mac

Add to `~/.ssh/config`:

```
Host openclaw
    HostName YOUR_VPS_IP
    User root
    IdentityFile ~/.ssh/id_ed25519
    LocalForward 28789 127.0.0.1:18789
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

Test connection: `ssh openclaw`

## Step 3: Security hardening

```bash
ssh openclaw
# Upload the project first
exit

# From your Mac:
scp -r ~/openclaw-project root@YOUR_VPS_IP:/root/

# SSH back in:
ssh openclaw
cd /root/openclaw-project
chmod +x infrastructure/secure.sh
./infrastructure/secure.sh
```

This configures UFW (SSH only), fail2ban, key-only SSH auth, and automatic security updates.

## Step 4: Deploy

```bash
chmod +x infrastructure/deploy.sh
./infrastructure/deploy.sh
```

This installs Docker, clones OpenClaw, sets up Sentinel's Python venv, and builds the Docker image.
By default it pins OpenClaw to the ref configured in `OPENCLAW_REF` (default in this repo: `v2026.2.22`).

## Step 5: Configure secrets

```bash
nano /root/openclaw/.env
```

Fill in all placeholder values:
- `OPENCLAW_GATEWAY_TOKEN` — strong random secret from your preferred secret manager/process
- `GOG_KEYRING_PASSWORD` — strong random secret from your preferred secret manager/process
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `GEMINI_API_KEY` — from Google AI Studio / Google Cloud (Gemini default routing)
- `OPENCLAW_TELEGRAM_TOKEN` — from @BotFather (assistant bot)
- `SENTINEL_TELEGRAM_TOKEN` — from @BotFather (sysadmin bot)
- `SENTINEL_ALLOWED_USERS` — your Telegram user ID
- `BRAVE_API_KEY` — required for full `ai_daily_brief` web grounding
- `OPENCLAW_REF` — pinned OpenClaw git commit/tag (keep default unless intentionally upgrading)

Important: assign plain values only in `.env` (no trailing inline comments after values).

Optional hardening: lock deployment source to a specific project commit:

```bash
export PROJECT_EXPECTED_REF="$(cd /root/openclaw-project && git rev-parse HEAD)"
```

Validate and sync Sentinel environment:

```bash
/root/openclaw-project/infrastructure/validate-placeholders.sh /root/openclaw/.env
/usr/local/sbin/sync-sentinel-env.sh
/usr/local/sbin/sync-openclaw-config.sh
```

Important:
- `OPENCLAW_TELEGRAM_TOKEN` and `BRAVE_API_KEY` in `/root/openclaw/.env` are propagated into the OpenClaw container environment.
- `sync-openclaw-config.sh` must preserve runtime ownership of `/root/.openclaw/openclaw.json` (the rollout script enforces this).

Optional provider sanity check (recommended):
```bash
BRAVE_API_KEY="$(grep '^BRAVE_API_KEY=' /root/openclaw/.env | cut -d= -f2-)"
curl -sS --compressed --get 'https://api.search.brave.com/res/v1/llm/context' \
  -H "X-Subscription-Token: ${BRAVE_API_KEY}" \
  --data-urlencode 'q=latest ai model release updates' \
  --data-urlencode 'count=3' \
  --data-urlencode 'maximum_number_of_tokens=2048' \
  --data-urlencode 'context_threshold_mode=balanced' | python3 -m json.tool | sed -n '1,60p'
```

Sentinel runs as a dedicated non-root `sentinel` user and reads `/etc/sentinel/sentinel.env`.
OpenClaw runtime config (`/root/.openclaw/openclaw.json`) is rendered from `.env` via `sync-openclaw-config.sh`.

## Step 6: Start services

```bash
# Start OpenClaw
cd /root/openclaw
docker compose up -d

# Verify it's running
docker compose logs -f
# Should see: "listening on ws://0.0.0.0:18789"
# Ctrl+C to exit logs

# Start Sentinel
systemctl start sentinel
systemctl status sentinel
journalctl -u sentinel -n 80 --no-pager

# Run full system checks
/root/openclaw-project/infrastructure/health-check.sh

# Run AI brief-specific smoke tests
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh
```

Before Telegram command testing, confirm smoke test includes:
- `Gateway runtime user can read /home/node/.openclaw/openclaw.json`
- `Telegram ingest runtime is running`
- `Gateway Telegram token source is ...` (not `none`)
- `Gateway container has BRAVE_API_KEY in environment` (unless intentionally running fallback mode)

Note: OpenClaw is a WebSocket gateway, so root HTTP probes can return `000`/`404` depending on route handling.  
The bundled health check validates Docker health status for the gateway container.

## Step 7: Verify via SSH tunnel

On your Mac, keep a tunnel open:

```bash
ssh -N -L 28789:127.0.0.1:18789 root@YOUR_VPS_IP
```

In another terminal, open a tokenized dashboard URL (required by Control UI auth):

```bash
RAW_URL="$(ssh root@YOUR_VPS_IP 'docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs dashboard --no-open | sed -n "s/^Dashboard URL: //p" | head -n1')"
URL="${RAW_URL/127.0.0.1:18789/127.0.0.1:28789}"
open -a "Safari" "$URL"
```

If browser shows `pairing required`, approve latest pending device request and refresh:

```bash
ssh root@YOUR_VPS_IP 'docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs devices approve --latest --json'
```

Then validate bots:
```bash
# Telegram: send /start to your OpenClaw bot
# Telegram: send /status to your Sentinel bot
# Telegram: send /ai_daily_brief status and /ai_daily_brief top5 to validate AI brief routing
```

Optional: route AI brief output to a dedicated Telegram channel (for example `@dandailybriefAI`):
```bash
cd /root/openclaw-project
./infrastructure/set-aibrief-output-channel.sh @dandailybriefAI
```
Then re-run:
```bash
./infrastructure/aibrief-smoke-test.sh
```
and validate in Telegram that `/ai_daily_brief top5` posts the full brief to the channel while DM shows ACK/status.

Important:
- DM invocation is always supported.
- Channel/supergroup invocation is supported only for IDs present in `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS`.
- `set-aibrief-output-channel.sh` auto-adds numeric output channels to `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` for interactive command use.
- If commands are sent as channel/anonymous identity, enable:
  - `OPENCLAW_TELEGRAM_INTERACTIVE_ALLOW_ANY_SENDER=1`
  - `OPENCLAW_TELEGRAM_NATIVE_COMMANDS=0`

## Step 8: Post-deployment

1. Set provider spending limits (Gemini primary budget; Anthropic is manual-only, no auto-fallback)
2. Set up backup cron:
   ```bash
   crontab -e
   # Add: 0 3 * * * /root/openclaw-project/infrastructure/backup.sh
   ```
3. Monitor API usage for the first 24 hours at console.cloud.google.com (primary) and console.anthropic.com (manual only)

## Fast AI Brief Config Rollout (post-deploy updates)

When only AI brief config/skills/state changed in this repo:

```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

This path avoids a full redeploy and only syncs AI brief assets, restarts services, and verifies health.
