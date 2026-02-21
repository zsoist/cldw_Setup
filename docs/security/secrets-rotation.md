# Secrets Rotation Policy

This project uses API tokens and credentials for OpenClaw + Sentinel operations.  
Treat all secrets as short-lived operational material.

## Rotation Schedule

- **Monthly:** rotate all bot and gateway tokens.
- **Quarterly:** rotate `GOG_KEYRING_PASSWORD` and any long-lived service credentials.
- **Immediate rotation required when:**
  - A secret appears in terminal history, logs, chat transcripts, screenshots, or git.
  - Unauthorized access is suspected.
  - A team member with secret access leaves the project.

## Secrets In Scope

- `ANTHROPIC_API_KEY`
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_TELEGRAM_TOKEN`
- `SENTINEL_TELEGRAM_TOKEN`
- `GOG_KEYRING_PASSWORD`

## Rotation Procedure

1. Generate new secret values using your standard secret generation method.
2. Update `/root/openclaw/.env`.
3. Validate values:
   - `/root/openclaw-project/infrastructure/validate-placeholders.sh /root/openclaw/.env`
4. Sync Sentinel environment:
   - `/usr/local/sbin/sync-sentinel-env.sh`
5. Restart services:
   - `cd /root/openclaw && docker compose up -d --force-recreate`
   - `systemctl restart sentinel`
6. Run health checks:
   - `/root/openclaw-project/infrastructure/health-check.sh`

## Logging and Handling Rules

- Never commit secrets to git.
- Never paste secrets into issue trackers or chat.
- Avoid exporting secrets globally in interactive shells.
- Prefer scoped environment files with strict permissions.
