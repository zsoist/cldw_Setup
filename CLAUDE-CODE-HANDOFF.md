# Claude Code Handoff: OpenClaw + Sentinel

> For the next LLM session.
>
> Last updated: 2026-02-23
> Branch: `main`
> Current commit: run `git rev-parse --short HEAD` on your checkout

---

## Current State

`main` now includes the 2026-02-22 hardening pass plus the 2026-02-23 AI Daily Brief channel-command/quality improvements and the 2026-02-23 Gemini integration pass.

Precedence rule: if historical notes below conflict, treat the **Latest pass (Gemini integration + cross-provider fallback)** as authoritative.

### Latest pass (2026-02-23, Gemini integration + cross-provider fallback)

- OpenClaw version pin updated to latest stable tag:
  - `OPENCLAW_REF` defaults in `infrastructure/env.template`, `infrastructure/docker-compose.yml`, `infrastructure/Dockerfile`, and `infrastructure/deploy.sh` now point to `v2026.2.22`.
- `infrastructure/env.template`
  - added `GEMINI_API_KEY` and `SENTINEL_PROVIDER` placeholders.
- `infrastructure/docker-compose.yml`
  - now injects `GEMINI_API_KEY` into `openclaw-gateway` runtime env.
- `infrastructure/sync-sentinel-env.sh`
  - now syncs `SENTINEL_PROVIDER` and `GEMINI_API_KEY` into `/etc/sentinel/sentinel.env`.
- `openclaw/openclaw-config.json`
  - model routing updated to:
    - primary: `google/gemini-2.5-flash`
    - fallbacks: `anthropic/claude-haiku-4-5`, `anthropic/claude-sonnet-4-6`
  - image routing + alias:
    - image primary: `google/gemini-2.5-pro`
    - image fallback: `google/gemini-2.5-flash`
    - alias: `nano-banana-pro -> google/gemini-2.5-pro`
- `openclaw/config/AGENTS.md`
  - 4-tier routing policy now documents:
    - default: Gemini Flash
    - standard: Gemini Pro
    - premium: Sonnet 4.6
    - manual: Opus 4.6
  - fallback chain updated to cross-provider order.
- `openclaw/config/SOUL.md`
  - added model escalation policy (Flash -> Pro -> Sonnet; Opus manual-only).
  - added retry policy (max 1 retry/step, 2/task, no unchanged retries).
- `openclaw/config/TOOLS.md`
  - added budget guidance (`$0.25` soft cap/task, `$0.75` hard cap/task, `<$5/day` target).
- Skills model overrides:
  - now Flash: `daily-briefing`, `task-tracker`, `ai-daily-brief-status`
  - now Pro: `ai-daily-brief`, `ai-daily-brief-morning`, `ai-daily-brief-evening`, `ai-daily-brief-top5`, `ai-daily-brief-builder`, `ai-daily-brief-watchlist`, `research-assistant`
  - `ai-daily-brief` status block now reports Gemini Flash/Pro + Sonnet/Opus hierarchy.
- Docs updated:
  - `docs/setup/model-routing-policy.md` rewritten for Gemini-first tiers and fallback chain.
  - `docs/COST-MANAGEMENT.md` target updated to `$6-15` LLM spend (`$14-23` total monthly).
  - `docs/DEPLOYMENT.md` now requires `GEMINI_API_KEY` in secrets setup.
  - `docs/TROUBLESHOOTING.md` now includes Gemini key/fallback/Claude-only checks.
- Sentinel provider support:
  - added Google provider option (`SENTINEL_PROVIDER=google`) with Anthropic default.
  - added Gemini API key validation path.
  - implemented provider abstraction in `sentinel/sentinel.py` for Anthropic + Gemini function-calling loops.
  - added Google function declaration schema in `sentinel/tools.py`.
  - updated tests/fixtures for dual-provider config and mocks.

### Latest pass (2026-02-23, VPS stability + Sentinel deployment drift fix)

- `infrastructure/vps-rollout-aibrief.sh`
  - now refreshes helper scripts in `/usr/local/sbin` from the repo before execution (`sync-sentinel-env.sh`, `sync-openclaw-config.sh`) so runtime sync behavior can't drift from git state.
  - now syncs Sentinel runtime code (`config.py`, `sentinel.py`, `telegram_handler.py`, `tools.py`, `requirements.txt`) into `/opt/sentinel` during config-only rollouts.
  - now refreshes Sentinel Python dependencies when `requirements.txt` changes, preventing stale runtime code after repo updates.
- `sentinel/sentinel.py`
  - added provider failover logic for recoverable primary-provider errors:
    - when primary provider is unavailable/auth-failing/rate-limited, Sentinel falls back to the other initialized provider for that request.
    - adds 5-minute primary-provider backoff to avoid repeated slow failures.
  - keeps configured primary preference, but improves uptime under upstream provider incidents and invalid key states.
- `sentinel/tests/test_provider_fallback.py`
  - adds coverage for Anthropic->Gemini fallback, fallback backoff behavior, and non-recoverable error pass-through.

### Latest pass (2026-02-23, AI Daily Brief latency + Brave budget optimization)

- `openclaw/skills/ai-daily-brief/SKILL.md`
  - switched to latency-first Brave retrieval profile:
    - full `14/6144`, top5 `8/3072`, builder `12/5120`, watchlist `8/2048`
  - adaptive Brave fan-out:
    - query #1 always
    - query #2 only when coverage is weak (instead of always mandatory)
  - explicit rule: no verbose pipeline narration unless `/ai_daily_brief status` is requested.
  - explicit rule: never report "python tools unavailable/manual curation mode" for normal runs.
  - tightened runtime budget targets (`top5 <45s`, full `<60s`).
- `openclaw/skills/ai-daily-brief-top5/SKILL.md`
  - mirrored adaptive fan-out and no-manual-narration/no-python-unavailable rules.
- `openclaw/workspace/logs/ai-brief-state.json`
  - default Brave/performance profile updated to optimized values.
  - state version bumped to `2026-02-23-v4`.
- `infrastructure/merge-ai-brief-state.sh`
  - now migrates legacy state defaults (`2026-02-22-v2`/`2026-02-23-v3`) to optimized Brave/performance defaults during rollout, instead of preserving slow legacy budgets forever.
- `infrastructure/env.template` + `infrastructure/docker-compose.yml`
  - default AIDB Brave budget env values aligned with optimized profile.
- docs updates:
  - `docs/playbooks/ai-daily-brief.md` and `docs/TROUBLESHOOTING.md` now document the latency profile and remediation path for slow top5 runs.

### Latest pass (2026-02-23, Brave LLM Context capability alignment)

- AI brief provider contract now explicitly aligns with Brave LLM Context API constraints/capabilities:
  - GET/POST support (POST preferred), query/parameter range guardrails, threshold mode policy by mode.
  - optional `goggles` support for source re-ranking.
  - local recall policy (`enable_local`) documented for explicit location-based use only.
  - mixed snippet handling (plain text + JSON-serialized structured blocks).
  - 1-second inter-query delay guidance to respect Brave sliding-window behavior.
- State schema advanced to `2026-02-23-v5` with Brave controls:
  - `request_method`, `goggles`, `threshold_by_mode`, `query_constraints`, `min_inter_query_delay_seconds`.
- `infrastructure/merge-ai-brief-state.sh`
  - now migrates older runtime state (`v2/v3/v4`) to `v5` and backfills new Brave config keys safely.
- `infrastructure/aibrief-smoke-test.sh`
  - now validates Brave config ranges/modes against Brave API limits and uses POST for LLM Context probe.

### Latest pass (2026-02-23, Channel commands + brief quality improvements)

Config version marker: `2026.02.23-channel-commands-v1`

#### Channel Command Fix (Item 1)
- `openclaw/config/CHANNELS.md`
  - Added 3-layer channel command setup guide (BotFather privacy mode, chat ID discovery, rollout).
  - Documents `@BotName` suffix format for privacy-mode-ON groups.
- `openclaw/config/SOUL.md`
  - Added `@BotName` suffix stripping rule: `/ai_daily_brief@MangenkyoBot` → `/ai_daily_brief`.
  - Added channel context rule: approved interactive chats treated identically to DM.
- `openclaw/config/AGENTS.md`
  - Added all new command modes to AI Brief Editor input format.
  - Added channel context + `@BotName` stripping note to Command Namespace Safety.
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - Added Channel Context section to Command Contract.
  - `@BotName` suffix normalization documented as mandatory pre-routing step.
- `infrastructure/aibrief-smoke-test.sh`
  - Added check: warns when `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` is empty (channel command invocation disabled).
- `docs/TROUBLESHOOTING.md`
  - Added "Channel commands not working" section with 3-layer fix guide, chat ID discovery command, BotFather privacy mode instructions.

#### Date Enforcement (Item 2)
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - Draft step: each story headline MUST include `YYYY-MM-DD` (ISO 8601) event date; `~YYYY-MM-DD (estimated)` allowed when inferred.
  - Validate step: date gate rejects stories without parseable dates.
  - Quality Gates: added explicit date gate.
- `openclaw/skills/ai-daily-brief-top5/SKILL.md`
  - Mirrored date enforcement rule.
- `docs/templates/ai-daily-brief-template.md`
  - Changed `<event date>` placeholder to `YYYY-MM-DD`.
- `docs/playbooks/ai-daily-brief.md`
  - Updated quality gates section with date gate.

#### Technical Depth (Item 3)
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - Draft step: mandatory Technical Details subsection per top story (architecture, params, context, capability delta, benchmarks with methodology, compute tier).
  - Validate step: technical depth gate added.
  - Status output: System model info block added (Haiku 4.5 / Sonnet 4.5 / Opus 4.6 with architecture + context specs, ranking weights, Brave API endpoint, cache TTL alignment).
  - Story structure example added (Gemini 2.5 Pro example with full technical details format).
- `openclaw/skills/ai-daily-brief-top5/SKILL.md`
  - Added technical one-liner requirement per story.
- `docs/templates/ai-daily-brief-template.md`
  - Added Technical Details subsection with all required fields.
- `docs/playbooks/ai-daily-brief.md`
  - Updated Output Modes and Quality Gates to require technical depth.

#### New Commands + Improvements (Item 4)
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - Added: `watchlist add/remove`, `feedback`, `history`, `diff`, `help` modes.
  - Pipeline step 12: story persistence to monthly JSON archive.
  - Pipeline step 13 (was 12): finalize now writes `cost_estimate`, appends `history[]`, updates `last_probe_at`.
  - Status output: watchlist topics, feedback summary, cost estimate, interactive chats registered.
- `openclaw/workspace/logs/ai-brief-state.json`
  - Schema v3: added `history[]`, `feedback[]`, `cost_estimate` in `last_run`, `last_probe_at` in `providers.brave_llm_context`.
- `openclaw/config/HEARTBEAT.md`
  - Task 11: Brave provider health probe every 6h (08:00/14:00/20:00 COT).
  - State rules: added cost_estimate, history, last_probe_at, story archive writes after each successful run.
- `openclaw/config/CRON.md`
  - Added Job 15: Brave Provider Health Probe (every 6h, Haiku, state-only mutation).
  - Updated Job 14 format note to include YYYY-MM-DD dates and Technical Details.
- `openclaw/config/AGENTS.md`
  - Updated AI Brief Editor input format with all new commands and model routing for lightweight modes.
- `README.md`
  - Updated AI Daily Brief section with all new commands, state schema v3, story archive, Brave probe, channel setup pointer.
  - Updated cron table from 14 → 15 jobs.

### Previous pass (2026-02-22, Telegram AI brief invocation hardening)
- `infrastructure/sync-openclaw-config.sh`
  - now accepts fallback token source `TELEGRAM_BOT_TOKEN` when `OPENCLAW_TELEGRAM_TOKEN` is absent.
  - exports `TELEGRAM_BOT_TOKEN` for runtime parity.
  - now writes `/root/.openclaw/secrets/telegram-default.token` and sets both:
    - `channels.telegram.tokenFile`
    - `channels.telegram.accounts.default.tokenFile`
  - token file is written without trailing newline and permissioned/chowned with runtime config files.
  - now maps Telegram DM authorization from `OPENCLAW_TELEGRAM_ALLOW_FROM` (fallback: `OPENCLAW_ALLOWED_USERS`, then `SENTINEL_ALLOWED_USERS`).
  - now maps approved channel/supergroup interaction targets from `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` into `channels.telegram.groups` with `requireMention=false`.
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
  - now validates runtime SOUL/AGENTS policy contains direct in-lane `/ai_daily_brief*` execution rules (catches stale sub-agent-only policy drift).
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - status mode now has strict truth rules: pairing/sub-agent blockage can only be reported with explicit current runtime evidence.
  - top5 now enforces explicit time scopes (`12h`, `week`, `month`, `month YYYY-MM`) and rejects out-of-scope stories.
  - source references must be clickable markdown hyperlinks.
  - top stories must include concrete model/product names when known (or explicitly marked undisclosed).
- `infrastructure/reset-telegram-offset.sh`
  - new recovery script: backs up and removes `/root/.openclaw/telegram/update-offset-<account>.json`, restarts gateway, and tails Telegram startup logs.
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - canonical skill now owns only `/ai_daily_brief` trigger (aliases removed to avoid non-deterministic native command routing).
- `openclaw/skills/ai-daily-brief-top5/SKILL.md`
  - alias model switched to `haiku` for lower-latency/manual diagnostics and reduced Sonnet rate-limit exposure.
  - top5 alias now accepts explicit scope suffixes and enforces hyperlink/model-name output rules.
- `openclaw/skills/ai-daily-brief-status/SKILL.md`
  - alias model switched to `haiku` so status diagnostics remain available when Sonnet is throttled.
- `openclaw/config/SOUL.md` + `openclaw/config/AGENTS.md`
  - `/ai_daily_brief*` command path now executes directly in-lane; no mandatory sub-agent spawn dependency.
- `openclaw/config/CRON.md`
  - AI brief automation schedules now:
    - daily `07:00` COT top5 previous 12h
    - daily `19:00` COT top5 previous 12h
    - Sunday `20:00` COT weekly top5 recap
    - day 1 `20:00` COT monthly top5 recap for previous month
- `infrastructure/set-aibrief-output-channel.sh`
  - when output channel is numeric chat ID, script now also updates `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` in env.
- `openclaw/config/CHANNELS.md`
  - Telegram policy now supports DM + approved interactive channel/supergroup chats instead of DM-only policy.

### Incident Status (resolved)
- Telegram command ingestion is healthy (`channels.status` account `running=true`, token source `tokenFile`).
- `/ai_daily_brief_status` returns diagnostics from state/provider config.
- `/ai_daily_brief_top5` invocation path is unblocked by pairing/sub-agent gate after in-lane policy fix.
- Live validation confirmed:
  - inbound `/commands` updates Telegram offset state
  - `/ai_daily_brief_top5` mutates `last_run` and produces output
  - Top 5 output now includes clickable links and explicit model/product naming when available
- Remaining runtime failures should now present as concrete provider/model/tool errors rather than generic pairing text.

### Dashboard Access Status (resolved)
- Control UI authentication requires tokenized URL (`#token=...`) and device approval.
- `token_missing` and `pairing required` browser errors are resolved by:
  1. opening dashboard URL generated by `openclaw.mjs dashboard --no-open`
  2. approving pending device with `openclaw.mjs devices approve --latest --json`
- After approval, dashboard sessions connect without repeated auth errors.

### Production outcome target
- OpenClaw gateway should run healthy via Docker health checks.
- Sentinel now runs as a **dedicated non-root user**.
- Env handling split:
  - Primary edit source: `/root/openclaw/.env`
  - Sentinel runtime env: `/etc/sentinel/sentinel.env` (synced via script)
- Backup/restore workflows hardened.
- AI Daily Brief capability now runs scoped automation (daily 12h top5, weekly recap, monthly recap) with stateful duplicate suppression.
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

- Runtime markdown configs are version-marked.
- Current marker pattern is intentionally mixed:
  - AI brief hot-path files use `2026.02.22-ai-brief-v4`
  - baseline files remain `2026.02.21-main-hardening`

Marker format:
`<!-- config-version: YYYY.MM.DD-label -->`

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

### From 2026-02-23 pass (channel commands + quality improvements)
1. **Enable channel commands (VPS runtime):**
   - Disable BotFather privacy mode OR train users to use `/command@MangenkyoBot` format.
   - Get supergroup chat ID and set `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` in `.env`.
   - Run rollout + smoke test: `smoke test must pass "Interactive Telegram chats registered for command invocation"`.
   - See `openclaw/config/CHANNELS.md` for the complete 3-step guide.
2. **Test new commands from Telegram after rollout:**
   - `/ai_daily_brief help` — should return full command reference
   - `/ai_daily_brief watchlist add "mistral ai"` — confirm state update
   - `/ai_daily_brief history 3` — confirm last 3 runs shown
   - `/ai_daily_brief feedback <run_id> 4 good signal-to-noise` — confirm recorded
   - `/ai_daily_brief diff` — confirm new/dropped story delta reported
3. **Test channel invocation:**
   - From registered supergroup: `/ai_daily_brief@MangenkyoBot status` → should return diagnostics
   - From registered supergroup: `/ai_daily_brief status` (if privacy mode disabled) → should work
4. **Verify Technical Details in brief output:**
   - Run `/ai_daily_brief top5 12h` — each story should include Architecture + Context + Benchmarks.
   - If sources don't expose technical details, `not publicly disclosed` should appear.
5. **Verify YYYY-MM-DD dates in story headlines:**
   - Check output of next scheduled run at 07:00 or 19:00 COT.
   - Any story without a date in the headline is a validation failure — check SKILL.md is loaded in runtime workspace.
6. **Brave health probe validation:**
   - After first heartbeat cycle at 08:00 COT: check `providers.brave_llm_context.last_probe_at` in state is non-null.
7. **Story archive validation:**
   - After first successful brief run: check `workspace/outputs/summaries/ai-brief-stories-YYYY-MM.json` exists.
8. **Merge state schema v3 into runtime:**
   - Run `infrastructure/merge-ai-brief-state.sh` to add new fields (`history`, `feedback`, `cost_estimate`) to the live VPS state file without overwriting existing `last_run` / `watchlist` data.

### From 2026-02-22 pass (Telegram invocation hardening)
9. Run full Sentinel test suite in a venv with Telegram dependency installed.
10. Rotate all exposed secrets immediately if any were ever posted in logs/chat.
11. Validate real VPS migration path for non-root Sentinel (`sync-sentinel-env.sh` + systemd restart).
12. Validate Brave provider health:
    - set `BRAVE_API_KEY` in `/root/openclaw/.env`
    - run `infrastructure/aibrief-smoke-test.sh`
    - confirm Brave LLM Context probe passes
13. Validate Telegram ingest runtime:
    - smoke test must pass `Gateway runtime user can read /home/node/.openclaw/openclaw.json`
    - smoke test must pass `Runtime config has Telegram auth material (botToken/tokenFile) at channels.telegram(.accounts.default)`
    - smoke test must pass `Telegram ingest runtime is running`
    - if smoke test shows `tokenSource=none`, re-run:
      - `bash /root/openclaw-project/infrastructure/sync-openclaw-config.sh /root/openclaw/.env /root/openclaw-project/openclaw/openclaw-config.json`
      - then recreate gateway container
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

# Dashboard auth/pairing recovery
RAW_URL="$(docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs dashboard --no-open | sed -n 's/^Dashboard URL: //p' | head -n1)"
echo "$RAW_URL"
docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs devices approve --latest --json

# If provider unconfigured, set Brave key then rerun smoke test
sed -i '/^BRAVE_API_KEY=/d' /root/openclaw/.env
echo 'BRAVE_API_KEY=YOUR_REAL_KEY' >> /root/openclaw/.env
cd /root/openclaw && docker compose up -d --force-recreate
cd /root/openclaw-project && ./infrastructure/aibrief-smoke-test.sh
```
