# Claude Code Handoff: OpenClaw + Sentinel

> For the next LLM session.
>
> Last updated: 2026-02-22  
> Branch: `main`  
> Current commit: run `git rev-parse --short HEAD` on your checkout  

---

## Current State

`main` now includes a full security/ops hardening pass plus AI Daily Brief v2 routing/ops improvements.

### Latest hotfix (2026-02-22, Telegram ingest + runtime env hardening)
- `infrastructure/sync-openclaw-config.sh`
  - now accepts fallback token source `TELEGRAM_BOT_TOKEN` when `OPENCLAW_TELEGRAM_TOKEN` is absent.
  - exports `TELEGRAM_BOT_TOKEN` for runtime parity.
  - now writes `/root/.openclaw/secrets/telegram-default.token` and sets both:
    - `channels.telegram.tokenFile`
    - `channels.telegram.accounts.default.tokenFile`
  - token file is written without trailing newline and permissioned/chowned with runtime config files.
  - now maps Telegram DM authorization from `OPENCLAW_TELEGRAM_ALLOW_FROM` (fallback: `OPENCLAW_ALLOWED_USERS`, then `SENTINEL_ALLOWED_USERS`).
  - now derives `channels.telegram.dmPolicy`:
    - explicit `OPENCLAW_TELEGRAM_DM_POLICY` if set
    - otherwise `allowlist` when allowFrom IDs exist
    - otherwise `pairing`
  - owner resolution now prioritizes explicit uid/gid or runtime container uid/gid (instead of inheriting root from freshly-written files), preventing drift when script runs outside full deploy.
- `infrastructure/docker-compose.yml`
  - now injects `TELEGRAM_BOT_TOKEN` / `OPENCLAW_TELEGRAM_TOKEN` and `BRAVE_API_KEY` (plus AIDB Brave tuning vars) into the gateway container env.
  - AIDB Brave tuning vars now have safe defaults to avoid noisy compose warnings when optional keys are omitted.
  - gateway startup now waits for mounted runtime config readiness (up to 30s) and clears Telegram webhook state before launching polling ingest.
- `infrastructure/vps-rollout-aibrief.sh`
  - passes runtime UID/GID into config sync.
  - now resolves docker compose runtime UID/GID from inside `/root/openclaw` (not via `-f` from another cwd), reducing env interpolation drift.
  - now validates Brave key shape (`len < 20` warning) before claiming provider readiness.
  - reapplies ownership/chmod after sync to keep config readable by the gateway runtime user.
  - now syncs updated `infrastructure/docker-compose.yml` into `/root/openclaw/docker-compose.yml` during config-only rollout.
  - post-rollout gateway health RPC now prefers `gateway.auth.token` from `/root/.openclaw/openclaw.json` and only falls back to `.env` (with explicit mismatch warning).
  - post-rollout diagnostics now include Telegram token field lengths/paths when `tokenSource=none`.
  - rollout now checks Telegram `getWebhookInfo`; if URL is active it clears webhook, restarts gateway, and rechecks health.
  - Telegram runtime diagnostics now use `gateway call channels.status` (live channel runtime) instead of relying on `health` snapshot fields.
  - rollout now surfaces per-account runtime details (`accountId`, `configured`, `running`, `tokenSource`, `lastInboundAt`, `lastOutboundAt`) and warns about stale update-offset risk.
- `infrastructure/deploy.sh`
  - same post-sync ownership fix during full deploy.
- `infrastructure/aibrief-smoke-test.sh`
  - now checks runtime readability of `/home/node/.openclaw/openclaw.json`.
  - now checks whether Telegram auth material exists in runtime config (`botToken` and/or `tokenFile`) and validates tokenFile readability inside the container.
  - now checks Telegram DM auth posture (`dmPolicy` + `allowFrom`) to catch non-invoking command setups.
  - now checks container-visible Telegram token env and Brave env.
  - now prefers gateway auth token from runtime config for `gateway call health`; `.env` token is fallback only (with mismatch diagnostics).
  - now fails when Telegram webhook is active (explicit polling conflict condition).
  - now fails fast for invalid/truncated Brave keys (`len < 20`).
  - improved Brave failure diagnostics (`key_len=...` when both probes fail).
  - Telegram runtime assertions now come from `channels.status` account snapshots (not `health` channel summary defaults).
  - warns when Telegram has no inbound activity and update-offset state may be silently blocking command ingest.
  - now validates that `/ai_daily_brief*` slash triggers have unique single-skill ownership (detects ambiguous duplicate trigger mappings).
  - now **fails hard** on `dmPolicy=pairing` with empty `allowFrom` (previously warning-only), because this silently blocks DM command invocation.
- `infrastructure/reset-telegram-offset.sh`
  - new recovery script: backs up and removes `/root/.openclaw/telegram/update-offset-<account>.json`, restarts gateway, and tails Telegram startup logs.
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - canonical skill now owns only `/ai_daily_brief` trigger (aliases removed to avoid non-deterministic native command routing).
- `openclaw/skills/ai-daily-brief-top5/SKILL.md`
  - alias model switched to `haiku` for lower-latency/manual diagnostics and reduced Sonnet rate-limit exposure.
- `openclaw/skills/ai-daily-brief-status/SKILL.md`
  - alias model switched to `haiku` so status diagnostics remain available when Sonnet is throttled.

### Production outcome target
- OpenClaw gateway should run healthy via Docker health checks.
- Sentinel now runs as a **dedicated non-root user**.
- Env handling split:
  - Primary edit source: `/root/openclaw/.env`
  - Sentinel runtime env: `/etc/sentinel/sentinel.env` (synced via script)
- Backup/restore workflows hardened.
- AI Daily Brief capability now runs twice daily with stateful duplicate suppression.
- AI Daily Brief now uses canonical `/ai_daily_brief` command arguments, plus VPS rollout/smoke-test scripts.
- AI Daily Brief supports dedicated Telegram delivery target via `config.output_channel` in state.
- AI Daily Brief now expects Brave LLM Context grounding (`BRAVE_API_KEY`) and reports provider diagnostics in smoke tests.
- AI brief runtime state path is absolute: `/home/node/.openclaw/workspace/logs/ai-brief-state.json` (avoid relative-path drift).
- Critical runtime path fix: workspace bootstrap files must be synced to `/root/.openclaw/workspace/*.md` (not only `/root/.openclaw/*.md`) so OpenClaw actually loads custom SOUL/AGENTS routing.

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
  - includes optional `config.output_channel` routing target
- Updated orchestration and schedules:
  - `openclaw/config/AGENTS.md` (canonical `/ai_daily_brief` routing + collision guard)
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
  - `infrastructure/merge-ai-brief-state.sh` (preserves runtime AI brief state across deploy/rollout)
  - `infrastructure/set-aibrief-output-channel.sh` (sets channel target safely)

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
- `infrastructure/merge-ai-brief-state.sh`
- `infrastructure/set-aibrief-output-channel.sh`
- `infrastructure/sync-sentinel-env.sh`
- `infrastructure/validate-placeholders.sh`
- `README.md`
- `openclaw/skills/ai-daily-brief/SKILL.md`
- `openclaw/workspace/logs/ai-brief-state.json`
- `infrastructure/env.template`
- `docs/playbooks/ai-daily-brief.md`
- `docs/templates/ai-daily-brief-template.md`

---

## Known Follow-up Items

1. Run full Sentinel test suite in a venv with Telegram dependency installed.
2. Rotate all exposed secrets immediately if any were ever posted in logs/chat.
3. Validate real VPS migration path for non-root Sentinel (`sync-sentinel-env.sh` + systemd restart).
4. Consider adding signed release artifacts if repo integrity is part of threat model.
5. Validate AI brief command flow in Telegram:
   - `/ai_daily_brief`
   - `/ai_daily_brief top5`
   - `/ai_daily_brief builder`
   - `/ai_daily_brief status`
6. Validate AI brief channel routing:
   - set state target with `set-aibrief-output-channel.sh`
   - ensure OpenClaw bot is channel admin
   - verify full brief posts to channel and DM gets ACK/status
7. Validate Brave provider health:
   - set `BRAVE_API_KEY` in `/root/openclaw/.env`
   - run `infrastructure/aibrief-smoke-test.sh`
   - confirm Brave LLM Context probe passes
8. Validate Telegram ingest runtime:
   - smoke test must pass `Gateway runtime user can read /home/node/.openclaw/openclaw.json`
   - smoke test must pass `Runtime config has Telegram auth material (botToken/tokenFile) at channels.telegram(.accounts.default)`
   - smoke test must pass `Telegram ingest runtime is running`
   - if smoke test shows `tokenSource=none`, re-run:
     - `bash /root/openclaw-project/infrastructure/sync-openclaw-config.sh /root/openclaw/.env /root/openclaw-project/openclaw/openclaw-config.json`
     - then recreate gateway container
   - if smoke test logs a gateway token mismatch, remove duplicate `OPENCLAW_GATEWAY_TOKEN=` lines from `/root/openclaw/.env` and rerun rollout.
   - avoid using `openclaw doctor --fix` in rollout flow for AI brief routing

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

# Route full brief output to dedicated channel
./infrastructure/set-aibrief-output-channel.sh @dandailybriefAI

# Validate
./infrastructure/aibrief-smoke-test.sh

# If provider unconfigured, set Brave key then rerun smoke test
sed -i '/^BRAVE_API_KEY=/d' /root/openclaw/.env
echo 'BRAVE_API_KEY=YOUR_REAL_KEY' >> /root/openclaw/.env
cd /root/openclaw && docker compose up -d --force-recreate
cd /root/openclaw-project && ./infrastructure/aibrief-smoke-test.sh
```
