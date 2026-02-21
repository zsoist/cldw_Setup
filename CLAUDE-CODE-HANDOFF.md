# Claude Code Handoff: OpenClaw + Sentinel

> For the next LLM session.
>
> Last updated: 2026-02-21  
> Branch: `main`  
> Current commit: run `git rev-parse --short HEAD` on your checkout  
> Source branch merged into main: `claude/openclaw-optimization-readme-f9ha4`

---

## Current Outcome (Production State)

Deployment on Hetzner VPS (`46.225.170.60`) is now operational:

- OpenClaw container: `Up (healthy)`
- Sentinel service: `active (running)`
- Backup script: working, backup tarballs present in `/root/backups`
- UFW + fail2ban: active
- Health check (after script fix): `8 passed, 0 failed`

OpenClaw is running as a WebSocket gateway (`ws://0.0.0.0:18789` in container), with host mapping `127.0.0.1:18789`.

---

## What Was Broken and How It Was Fixed

### 1. Sentinel failed to start from `.env` values

Root cause:
- Inline comments were appended to `.env` secrets and IDs, e.g.:
  - `SENTINEL_ALLOWED_USERS=12345 # comment`
  - `SENTINEL_TELEGRAM_TOKEN=... # comment`

Fixes:
- `sentinel/config.py` now tolerates inline comments and trims values.
- Deployment docs now explicitly require plain values in `.env`.

### 2. OpenClaw Docker build failed (`npm ci` lockfile mismatch)

Root cause:
- Upstream OpenClaw at pinned ref uses pnpm workspace; `npm ci` was invalid.

Fixes:
- `infrastructure/Dockerfile` updated to:
  - Node 22 base
  - `corepack enable`
  - `pnpm install --frozen-lockfile`
  - `pnpm build`
  - `pnpm ui:build`

### 3. OpenClaw gateway crash-looped on config validation

Root cause:
- `openclaw/openclaw-config.json` used legacy keys unsupported by pinned OpenClaw ref:
  - `agents.profiles`
  - `channels.telegram.token`
  - `channels.telegram.groupChats`
  - root `heartbeat`, `providers`, `security`

Repository fix on `main`:
- `openclaw/openclaw-config.json` now ships a schema-valid configuration for pinned OpenClaw.
- Deploy now copies this valid schema to both runtime config targets.

VPS operational fix (already applied before repo fix):
- Replaced `/root/.openclaw/openclaw.json` with schema-valid config using:
  - `gateway.mode`
  - `gateway.bind`
  - `gateway.auth.token`
  - `agents.defaults.*`
  - `channels.telegram.botToken` + `groups`

### 4. OpenClaw state permissions caused write failures

Root cause:
- `deploy.sh` forced `/root/.openclaw` ownership to `1000:1000`, which may not match the image's `openclaw` user UID/GID.
- On some hosts this caused EACCES during session/credentials/state writes.

Fix:
- `infrastructure/deploy.sh` now resolves the built image runtime UID/GID dynamically and chowns `/root/.openclaw` accordingly.
- Deploy also pre-creates required state dirs (`agents/main/sessions`, `credentials`) and applies strict config permissions.
### 5. Health check false-negative for OpenClaw HTTP

Root cause:
- Health script used HTTP root probe (`curl /`) for a WS gateway path and marked healthy gateway as failed.

Fix:
- `infrastructure/health-check.sh` now checks Docker container health status instead of raw HTTP root code.
- `sentinel/tools.py` (`check_openclaw_health`) now reports Docker health and no longer relies on root HTTP status.

---

## Important Reality About OpenClaw Health

For this deployment, root HTTP code is not reliable as readiness signal.
Use either:

1. `docker inspect` health status on `openclaw-openclaw-gateway-1`
2. Gateway RPC health call:

```bash
TOKEN=$(grep '^OPENCLAW_GATEWAY_TOKEN=' /root/openclaw/.env | cut -d= -f2-)
docker exec -it openclaw-openclaw-gateway-1 \
  node openclaw.mjs gateway call health --url ws://127.0.0.1:18789 --token "$TOKEN" --json
```

---

## Files Most Relevant to Continue Work

- `infrastructure/health-check.sh`
- `infrastructure/Dockerfile`
- `infrastructure/deploy.sh`
- `infrastructure/env.template`
- `docs/DEPLOYMENT.md`
- `openclaw/openclaw-config.json`
- `sentinel/config.py`
- `sentinel/tools.py`
- `README.md`

---

## Remaining Work (Priority Order)

1. **Rotate exposed secrets immediately**
   - Anthropic API key
   - OpenClaw Telegram bot token
   - Sentinel Telegram bot token
   - OpenClaw gateway token
   - GOG keyring password

2. **Stabilize SSH access**
   - Ensure root key auth is correctly configured in `/root/.ssh/authorized_keys`.
   - Keep `ServerAliveInterval` and `ServerAliveCountMax` client options.

3. **Optional hardening cleanup**
   - Validate no duplicated keys in `.env`.
   - Add CI smoke checks for config schema + health-check behavior.

---

## Verified Commands (Known Good)

```bash
# OpenClaw + Sentinel status
cd /root/openclaw
docker compose ps
systemctl status sentinel --no-pager
/root/openclaw-project/infrastructure/health-check.sh

# OpenClaw gateway health (authoritative)
TOKEN=$(grep '^OPENCLAW_GATEWAY_TOKEN=' /root/openclaw/.env | cut -d= -f2-)
docker exec -it openclaw-openclaw-gateway-1 \
  node openclaw.mjs gateway call health --url ws://127.0.0.1:18789 --token "$TOKEN" --json
```

---

## Notes for Next LLM

- Do not trust historical failures in `journalctl` unless they are newer than the last restart.
- Treat latest state snapshots (`docker compose ps`, recent logs, current health check) as source of truth.
- If OpenClaw is `healthy` but HTTP root probe fails, this is expected in current topology.
