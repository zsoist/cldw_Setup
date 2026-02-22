# Claude Code Handoff: OpenClaw + Sentinel

> For the next LLM session.
>
> Last updated: 2026-02-22  
> Branch: `main`  
> Current commit: run `git rev-parse --short HEAD` on your checkout  

---

## Current State

`main` now includes a full security/ops hardening pass plus AI Daily Brief v2 routing/ops improvements.

### Production outcome target
- OpenClaw gateway should run healthy via Docker health checks.
- Sentinel now runs as a **dedicated non-root user**.
- Env handling split:
  - Primary edit source: `/root/openclaw/.env`
  - Sentinel runtime env: `/etc/sentinel/sentinel.env` (synced via script)
- Backup/restore workflows hardened.
- AI Daily Brief capability now runs twice daily with stateful duplicate suppression.
- AI Daily Brief now has dedicated `/aibrief*` namespace safeguards, expanded modes, and VPS rollout/smoke-test scripts.

---

## Major Changes in This Pass

### 1) Sentinel runtime hardening

- `sentinel/sentinel.service`
  - `User=sentinel`, `Group=sentinel`
  - `SupplementaryGroups=docker adm`
  - `EnvironmentFile=-/etc/sentinel/sentinel.env`
  - `KillMode=control-group`
  - `NoNewPrivileges=true`
  - `LogsDirectory=sentinel`

### 2) Sentinel abuse controls + auditability

- `sentinel/config.py`
  - Added bounded env-driven controls:
    - `SENTINEL_RATE_LIMIT_MAX_REQUESTS`
    - `SENTINEL_RATE_LIMIT_WINDOW_SECONDS`
    - `SENTINEL_CONVERSATION_TTL_SECONDS`
    - `SENTINEL_MAX_TOOL_ITERATIONS`

- `sentinel/sentinel.py`
  - Added per-user sliding-window rate limiting.
  - Added conversation TTL expiry/reset (reduces stale-context replay risk).
  - Added tamper-evident hash-chained audit log events (`/var/log/sentinel/audit.log`).
  - Removed silent `default=str` serialization masking.
  - Tool result truncation now explicit (`truncated`, `original_length`, `preview`).

### 3) Tooling security boundaries

- `sentinel/tools.py`
  - Host/url validation tightened (`ipaddress`, URL parsing, local HTTP validation).
  - Docker operations restricted to allowlisted container:
    - `openclaw-openclaw-gateway-1`
  - `docker` command whitelist tightened:
    - `docker ps --filter name=openclaw-openclaw-gateway-1`
    - `docker stats --no-stream openclaw-openclaw-gateway-1`
  - `check_openclaw_health` now reports docker health + HTTP fallback endpoint status.
  - Docker tool outputs normalized to structured dicts.

### 4) Backup/restore hardening

- `infrastructure/backup.sh`
  - Switched to explicit file allowlist backup collection.
  - Backup timestamp now ISO-like UTC format in filename.
  - Sensitive files excluded by policy (env/keys/certs/credentials paths).

- `infrastructure/restore.sh`
  - Archive validation now rejects non file/dir entry types.
  - Extracts to temp dir first, then copies allowlisted paths only.
  - Avoids direct blind extract to `/`.

### 5) Deployment integrity improvements

- `infrastructure/deploy.sh`
  - Added checksum-verified copy helper for critical file transfers.
  - Creates/updates `sentinel` system user and group assignments.
  - Installs `/usr/local/sbin/sync-sentinel-env.sh`.
  - Creates secure Sentinel dirs:
    - `/etc/sentinel`
    - `/var/log/sentinel`
    - `/var/backups/openclaw`
  - Still aligns OpenClaw state ownership to runtime UID/GID from built image.
  - Adds warning if SSH snippet placeholder still unresolved.

- Added scripts:
  - `infrastructure/sync-sentinel-env.sh`
  - `infrastructure/validate-placeholders.sh`

### 6) Config drift management

- Added version markers to all runtime markdown configs:
  - `openclaw/config/*.md`
  - `openclaw/agents/work/*.md`

Marker:
`<!-- config-version: 2026.02.22-ai-brief-v2 -->`

### 7) Documentation updates

- Updated:
  - `README.md`
  - `docs/DEPLOYMENT.md`
  - `docs/TROUBLESHOOTING.md`
- Added:
  - `docs/security/secrets-rotation.md`

### 8) AI Daily Brief capability

- Added new skill:
  - `openclaw/skills/ai-daily-brief/SKILL.md`
- Updated existing skill:
  - `openclaw/skills/daily-briefing/SKILL.md` (now daily planning-first; no duplicate AI headline synthesis)
- Added stateful AI brief tracking:
  - `openclaw/workspace/logs/ai-brief-state.json`
- Updated orchestration and schedules:
  - `openclaw/config/AGENTS.md` (explicit `/aibrief*` namespace ownership + collision guard)
  - `openclaw/config/CRON.md` (idempotent slot behavior + richer AI brief format targets)
  - `openclaw/config/HEARTBEAT.md` (partial-run logic + status diagnostic guidance)
- Added playbook/template:
  - `docs/playbooks/ai-daily-brief.md`
  - `docs/templates/ai-daily-brief-template.md`
- Deployment wiring:
  - `infrastructure/deploy.sh` now copies AI brief state file and reports 4 deployed skills.
- New operational scripts:
  - `infrastructure/vps-rollout-aibrief.sh` (config-only AI brief rollout on VPS)
  - `infrastructure/aibrief-smoke-test.sh` (health/token/state smoke tests)

---

## Files Most Relevant for Next Session

- `sentinel/sentinel.py`
- `sentinel/tools.py`
- `sentinel/config.py`
- `sentinel/sentinel.service`
- `infrastructure/deploy.sh`
- `infrastructure/backup.sh`
- `infrastructure/restore.sh`
- `infrastructure/health-check.sh`
- `infrastructure/vps-rollout-aibrief.sh`
- `infrastructure/aibrief-smoke-test.sh`
- `infrastructure/sync-sentinel-env.sh`
- `infrastructure/validate-placeholders.sh`
- `README.md`
- `openclaw/skills/ai-daily-brief/SKILL.md`
- `openclaw/workspace/logs/ai-brief-state.json`
- `docs/playbooks/ai-daily-brief.md`
- `docs/templates/ai-daily-brief-template.md`

---

## Known Follow-up Items

1. Run full Sentinel test suite in a venv with Telegram dependency installed.
2. Rotate all exposed secrets immediately if any were ever posted in logs/chat.
3. Validate real VPS migration path for non-root Sentinel (`sync-sentinel-env.sh` + systemd restart).
4. Consider adding signed release artifacts if repo integrity is part of threat model.
5. Validate AI brief command flow in Telegram:
   - `/aibrief`, `/aibrief_morning`, `/aibrief_evening`, `/aibrief_top5`, `/aibrief_builder`, `/aibrief_watchlist`, `/aibrief_status`

---

## Quick Operational Commands

```bash
# Validate env + sync Sentinel env
/root/openclaw-project/infrastructure/validate-placeholders.sh /root/openclaw/.env
/usr/local/sbin/sync-sentinel-env.sh

# Restart stack
cd /root/openclaw
docker compose up -d --force-recreate
systemctl daemon-reload
systemctl restart sentinel

# Verify
docker compose ps
systemctl status sentinel --no-pager
journalctl -u sentinel -n 100 --no-pager
/root/openclaw-project/infrastructure/health-check.sh
/root/openclaw-project/infrastructure/aibrief-smoke-test.sh

# Config-only AI brief rollout (no full redeploy)
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
```
