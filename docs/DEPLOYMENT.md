# Deployment Guide

Step-by-step guide for deploying OpenClaw + Sentinel on a Hetzner CPX22 VPS.

## Prerequisites

- Hetzner Cloud account
- SSH key pair generated (`ssh-keygen -t ed25519`)
- Anthropic API key from console.anthropic.com
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
    LocalForward 18789 127.0.0.1:18789
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
By default it pins OpenClaw to the commit configured in `OPENCLAW_REF` (see `.env`).

## Step 5: Configure secrets

```bash
nano /root/openclaw/.env
```

Fill in all placeholder values:
- `OPENCLAW_GATEWAY_TOKEN` — generate with `openssl rand -hex 32`
- `GOG_KEYRING_PASSWORD` — generate with `openssl rand -hex 32`
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `OPENCLAW_TELEGRAM_TOKEN` — from @BotFather (assistant bot)
- `SENTINEL_TELEGRAM_TOKEN` — from @BotFather (sysadmin bot)
- `SENTINEL_ALLOWED_USERS` — your Telegram user ID
- `OPENCLAW_REF` — pinned OpenClaw git commit/tag (keep default unless intentionally upgrading)

Important: assign plain values only in `.env` (no trailing inline comments after values).

Sentinel reads the same `/root/openclaw/.env` file via systemd `EnvironmentFile`.

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
```

## Step 7: Verify via SSH tunnel

On your Mac:
```bash
ssh openclaw  # This opens the tunnel automatically
```

In another terminal:
```bash
# Browser: open http://127.0.0.1:18789/
# Telegram: send /start to your OpenClaw bot
# Telegram: send /status to your Sentinel bot
```

## Step 8: Post-deployment

1. Set Anthropic spending limit to $25/month
2. Set up backup cron:
   ```bash
   crontab -e
   # Add: 0 3 * * * /root/openclaw-project/infrastructure/backup.sh
   ```
3. Monitor API usage for the first 24 hours at console.anthropic.com
