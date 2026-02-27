# Claude Code Handoff: OpenClaw + Sentinel

> For the next LLM session.
>
> Last updated: 2026-02-27
> Branch: `main`
> Current commit: run `git rev-parse --short HEAD` on your checkout
> **Start here:** Read `ARCHITECTURE.md` first for codebase navigation.

---

## Current State

`main` is current through **2026-02-27 (Model optimization + Expert Network Brief + cost optimization audit + docs overhaul)**. All services healthy on VPS.

Precedence rule: if historical notes below conflict, treat the **Latest pass (2026-02-27, Model Optimization)** as authoritative.

### Latest pass (2026-02-27, Model Optimization — Haiku Purge + Auto-Fallback Disabled)

Enforced model policy: Flash 2.5 = default for everything. Pro 2.5 = escalation for complex. Sonnet 4.6 = manual explicit only. Opus 4.6 = manual explicit only. **Haiku is NEVER used.**

**sentinel.py changes:**
- `_normalize_anthropic_model_name()` — All Haiku model aliases now map to `claude-sonnet-4-6`. No path returns Haiku.
- `_get_fallback_provider()` — Returns `None` always. Auto-fallback to Anthropic is DISABLED. If Gemini fails, retry once then error.

**Config/docs changes:**
- `openclaw/config/AGENTS.md` — Fallback chain replaced with "Model chain (no automatic fallback)", Haiku removed
- `openclaw/config/BOOT.md` — "Haiku defaults" → "Flash defaults"
- `docs/setup/model-routing-policy.md` — Cross-provider fallback replaced, Haiku purged
- `docs/TROUBLESHOOTING.md` — Updated Gemini unavailability behavior, clarified no auto-fallback
- `docs/DEPLOYMENT.md` — Clarified Anthropic is manual-only
- `docs/setup/performance-tuning.md` — "cheaper model (Haiku)" → "default model (Flash)"
- `docs/templates/research-summary-template.md` — Haiku → Flash
- `docs/playbooks/meeting-prep.md` — Haiku → Flash
- `docs/research/job-search-automation.md` — All Haiku → Flash
- `openclaw/workspace/logs/cron-job-results.md` — Haiku/Sonnet → Flash/Pro
- `infrastructure/aibrief-smoke-test.sh` — API key validation changed from Haiku to Sonnet
- `README.md` — "Anthropic fallbacks" → "Anthropic manual-only", 5 references updated

**Test changes:**
- `sentinel/tests/conftest.py` — `claude-haiku-4-5` → `claude-sonnet-4-6`
- `sentinel/tests/test_telegram.py` — All Haiku → Sonnet
- `sentinel/tests/test_provider_fallback.py` — All Haiku → Sonnet
- `sentinel/tests/test_cost_tracker.py` — All Haiku → Sonnet

**Kept (historical/defensive):**
- `sentinel/cost_tracker.py` — Haiku pricing entries retained for accurate historical cost accounting
- `sentinel/sentinel.py` — Haiku entries in alias_map retained as defensive remapping (Haiku → Sonnet)

**Deployed on VPS:** sentinel.py + tests synced to /opt/sentinel/, service restarted.

### Previous pass (2026-02-27, Expert Network Intelligence Brief)

New feature: competitive intelligence brief monitoring 8 expert network competitors for Dialectica.

**New files (repo):**
- `openclaw/skills/expert-network-brief/SKILL.md` — Main skill (Flash, ~8.5KB prompt)
- `openclaw/skills/expert-network-brief-status/SKILL.md` — Status alias

**Modified files (repo):**
- `openclaw/jobs.json` — Added 2 ENB cron jobs (AM=12:00 UTC, PM=23:00 UTC)
- `openclaw/config/SOUL.md` — Added ENB routing, alias normalization
- `openclaw/config/AGENTS.md` — Added Expert Network Intelligence Analyst agent, fixed heartbeat to 90m
- `README.md` — Added ENB section, updated cron table (3 jobs), updated project tree
- `ARCHITECTURE.md` — Added ENB skills, cron entries, state file to index
- `docs/TROUBLESHOOTING.md` — Added ENB troubleshooting section

**Deployed on VPS:**
- Skills synced to `/root/.openclaw/skills/expert-network-brief*/`
- State file created at `/root/.openclaw/workspace/logs/enb-state.json`
- Cron jobs in `/root/.openclaw/cron/jobs.json` (3 jobs total)
- SOUL.md and AGENTS.md updated in workspace
- Gateway reloaded via SIGUSR1 — no errors

**Cron schedule (all 3 jobs):**

| Job | UTC | COT | Model | Timeout |
|-----|-----|-----|-------|---------|
| AI Daily Brief Top5 | 10 12 * * * | 07:10 | Pro | 180s |
| ENB Morning (full scan) | 0 12 * * * | 07:00 | Flash | 120s |
| ENB Evening (delta) | 0 23 * * * | 18:00 | Flash | 90s |

**ENB cost profile:** ~$0.005/run × 2 runs/day = ~$0.30/month (Flash + 2-3 Brave calls).

**Competitors monitored:** GLG, AlphaSights, Guidepoint, Third Bridge, Capvision, Prospex, Coleman Research, Atheneum Partners + Dialectica (self).

---

### Latest pass (2026-02-27, Full cost optimization audit + documentation overhaul)

Comprehensive cost optimization audit across ALL code (Sentinel, OpenClaw, Job Radar, infrastructure) + full documentation rewrite.

**Sentinel — CRITICAL FIXES:**
1. **Token tracking fixed** — `_extract_google_usage()` was returning 0 for ALL Gemini calls. Proto objects use attributes, not dict keys. Fixed with direct `getattr()`.
2. **Zero-cost slash commands** — `/status`, `/openclaw`, `/security`, `/backup` now bypass LLM entirely (were costing ~1,940 tokens each). Added `/cost` command.
3. **Static responses expanded** — "thanks", "ok", "help", "ping" handled without LLM call.
4. **Tool descriptions trimmed** — ~50 tokens saved per API call.
5. **Tool result cap reduced** — 4000 → 2000 chars.

**OpenClaw — CRITICAL FIXES:**
1. **contextTokens reduced** — All sessions reset from 262K-1M to 65,536. Gateway default also reduced to 65,536.
2. **contextPruning enabled** — `cache-ttl` mode, 30m TTL, keepLastAssistants: 3, minPrunableToolChars: 50,000.
3. **Heartbeat interval increased** — 55m → 90m (fewer proactive checks).
4. **imageModel downgraded** — Pro → Flash.
5. **SOUL.md trimmed 63%** — 8,839 → 3,239 bytes (~800 tokens).
6. **Alias skills downgraded** — morning/evening/builder changed from Pro to Flash.
7. **Duplicate AGENTS.md deleted** — Was in both root and workspace (~3,700 extra tokens per call).
8. **Stale openclaw-config.json deleted** — Had Anthropic fallbacks that were auth-unconfigured.
9. **ai-brief-state.json pruned** — Removed stale failures and old stories.

**Job Radar — CRITICAL FIXES:**
1. **Health checks zero-cost** — Brave uses web search (not LLM Context), Anthropic uses empty-messages (zero tokens).
2. **llm_standard_model → Flash** — Default was Pro.
3. **Free connectors enabled** — `JOB_SEARCH_BRAVE_ONLY=false` (HN/RemoteOK now active).
4. **Health cache TTL 3h** — Was 120s, now 10,800s.
5. **Digest dedup fixed** — Content-based hash (was timestamp-based, so every run was unique).

**Infrastructure:**
1. **Docker cache pruned** — 37GB reclaimed. Weekly auto-prune cron added.
2. **Logrotate added** — Sentinel logs at `/etc/logrotate.d/sentinel`.
3. **Journald capped** — 100MB max, 2-week retention.
4. **.env permissions fixed** — 644 → 600.
5. **Backup cron verified** — Working.

**Documentation overhaul:**
1. **README.md** — Full rewrite reflecting current state (627 lines).
2. **ARCHITECTURE.md** — NEW: LLM-optimized codebase index for any agent.
3. **TROUBLESHOOTING.md** — Added: token tracking fix, zero-cost commands, health check fixes, disk space, contextPruning checks.

**Files changed (repo):**
- `sentinel/sentinel.py` — token tracking, static responses, tool result cap
- `sentinel/telegram_handler.py` — zero-cost slash commands, /cost handler
- `sentinel/tools.py` — trimmed tool descriptions, added cost_summary tool
- `openclaw/openclaw-config.json` — contextPruning, heartbeat 90m, imageModel Flash, contextTokens 65536
- `openclaw/skills/ai-daily-brief-morning/SKILL.md` — model Flash
- `openclaw/skills/ai-daily-brief-evening/SKILL.md` — model Flash
- `openclaw/skills/ai-daily-brief-builder/SKILL.md` — model Flash
- `README.md` — full rewrite
- `ARCHITECTURE.md` — new file
- `docs/TROUBLESHOOTING.md` — updated
- `docs/COST-MANAGEMENT.md` — updated

**Files changed on VPS (not in git):**
- `/root/.openclaw/openclaw.json` — contextPruning, heartbeat 90m, imageModel Flash, contextTokens 65536
- `/root/.openclaw/agents/main/sessions/sessions.json` — all sessions reset to contextTokens 65536
- `/root/.openclaw/workspace/SOUL.md` — trimmed 63%
- `/root/.openclaw/workspace/AGENTS.md` — deleted duplicate
- `/root/.openclaw/workspace/logs/ai-brief-state.json` — pruned stale data
- `/opt/sentinel/*.py` — all updated, chown sentinel:sentinel
- `/root/job-radar/.env` — BRAVE_ONLY=false, HEALTH_TTL=10800
- `/root/job-radar/backend/app/domain/health/checker.py` — zero-cost checks
- `/root/job-radar/backend/app/config.py` — llm_standard_model=Flash
- `/root/job-radar/backend/app/api/v1/digest.py` — content-based dedup
- `/etc/systemd/journald.conf` — capped 100M
- `/etc/logrotate.d/sentinel` — new

---

### Latest pass (2026-02-26, Job Radar + AI Daily Brief audit)

Full runtime audit of both subsystems. All fixes applied to VPS and committed/pushed to `main`.

**Job Radar — status: ALL HEALTHY (no changes required)**
- Health endpoint: all checks OK (`database`, `brave_api`, `anthropic_api`, `telegram_bot`, `openclaw_gateway`)
- AM digest sent at 13:00 UTC on 2026-02-26: 5 jobs, `message_id=87`, delivered to `-1003826801947`
- DB: 69 jobs, all with `company_name` populated, all scored (0 unscored)
- `BRAVE_CONTEXT_MAX_TOKENS=3072` confirmed in `/root/job-radar/.env`
- Digest schedule confirmed: AM=13:00 UTC (08:00 COT), PM=23:00 UTC (18:00 COT)
- No code or config changes needed

**AI Daily Brief — CRITICAL FIXES APPLIED:**

1. **`ai-brief-state.json` corrupted JSON** — `providers` block was closed with `]` instead of `}` at line 416. Caused by the cron job timing out mid-write at 60s. Fixed with Python string replacement:
   ```python
   old = '    }\n  ],\n  "recent_story_fingerprints"'
   new = '    }\n  },\n  "recent_story_fingerprints"'
   ```
   Verified with `json.loads()` before saving. File is now valid (16 history entries, 5 fingerprints, schema_version `2026-02-24-v7`).

2. **Stale `last_run.status="running"` lock** — run `top5-week-20260226-0710` was left `running` with `finished_at: null` (3282 seconds stale). Cleared via:
   ```bash
   bash /root/openclaw-project/infrastructure/reconcile-ai-brief-state.sh \
     /root/.openclaw/workspace/logs/ai-brief-state.json
   # RECOVERED run_id=top5-week-20260226-0710 reason=stale_age_seconds=3282
   ```

3. **Skills directory owned by `root:root`** — `rsync` ran as root and reset ownership. Fixed:
   ```bash
   chown -R sentinel:systemd-journal /root/.openclaw/skills/
   ```

**Expected self-healing on next cron run (2026-02-27 12:10 UTC):**
- `lastRunStatus: "error"`, `consecutiveErrors: 2` — will auto-reset on first successful run
- History shows last 6 runs as "failed" (all pre-fix failures from before 2026-02-26)
- `timeoutSeconds: 120` is now in effect — brief should complete within budget

**Files changed on VPS (not in git):**
- `/root/.openclaw/workspace/logs/ai-brief-state.json` — corrupted JSON fixed, stale lock cleared
- `/root/.openclaw/skills/` — ownership corrected to `sentinel:systemd-journal`

---

### Latest pass (2026-02-26, VPS sync + config hardening)

All fixes applied to running VPS and committed/pushed to `main` (commit `7a4fc5d` + this commit).

**What was broken:**

1. **VPS 7 commits behind GitHub** — Codex made commits on GitHub and edited files directly over SSH, leaving local repo diverged from both running services and GitHub. Fixed by pulling all 7 commits and deploying to `/opt/sentinel/` and `/root/.openclaw/`.

2. **`compaction.mode: "aggressive"` is INVALID** — OpenClaw schema only accepts `"default"` or `"safeguard"`. Every `SIGUSR1` reload logged `Invalid config: agents.defaults.compaction.mode: Invalid input` and the gateway silently kept running on its last good config. Fixed to `"safeguard"` in runtime `openclaw.json` and repo template `openclaw-config.json`.

3. **Anthropic model fallbacks causing errors** — Codex re-added `anthropic/claude-haiku-4-5` and `anthropic/claude-sonnet-4-6` to `model.fallbacks`. Anthropic auth is unconfigured in the OpenClaw gateway. Removed from both runtime config and repo template.

4. **Cron job timing out** — `jobs.json` had `timeoutSeconds: 60` which is too short for Gemini Flash to complete a daily brief with Brave search. Two consecutive error runs with `FailoverError: LLM request timed out`. Raised to `120`.

5. **`openclaw.json` permission drift** — Edit tool resets ownership to `root:root 600`. Container runs as uid=999 (`openclaw`) = same as `sentinel` uid=999, but access depends on permissions. Fixed to `640 sentinel:systemd-journal` after every edit. Also: `SIGUSR1` was sent while the file was temporarily root-owned, causing `EACCES` in logs.

6. **Stale placeholder group `-1001234567890`** — Removed from `groups` in runtime `openclaw.json`.

7. **Sentinel features missing from VPS** — `/opt/sentinel/` was behind GitHub by 7 commits, missing: `response.text` fallback for empty Gemini responses, usage footer on all Telegram replies, configurable `max_tokens` / `usd_to_cop_rate`, crash-safe cost tracking via `cost_tracker.py`.

8. **`/etc/sentinel/sentinel.env` missing vars** — Added `SENTINEL_MAX_TOKENS=768`, `SENTINEL_USD_TO_COP_RATE=4000`, and 8 cost-tracking env vars.

**Files changed on VPS (not tracked in git — apply manually after pulls):**
- `/opt/sentinel/*.py` — deployed from GitHub; `chown sentinel:sentinel` after every copy
- `/etc/sentinel/sentinel.env` — full current content in memory notes
- `/root/.openclaw/openclaw.json` — safeguard compaction, no Anthropic fallbacks, no placeholder group; `chown sentinel:systemd-journal` + `chmod 640` after every edit
- `/root/.openclaw/cron/jobs.json` — `timeoutSeconds: 120`
- `/root/.openclaw/skills/` — synced from `openclaw/skills/` in repo
- `/root/.openclaw/AGENTS.md`, `SOUL.md`, `MEMORY.md` — synced from `openclaw/config/` in repo

**Critical runtime rules (hard-won, do not repeat mistakes):**

| Rule | Detail |
|------|--------|
| `compaction.mode` | Only `"default"` and `"safeguard"` are valid in this OpenClaw build. `"aggressive"` is silently rejected. |
| `openclaw.json` ownership | Must be `640 sentinel:systemd-journal` after every edit. Edit tool always resets to `root:root 600`. |
| Sentinel `.py` ownership | Must be `sentinel:sentinel` after every copy/edit. |
| SIGUSR1 reload | If config is invalid, gateway runs silently on last good config. Check `docker logs` for `Invalid config` after reload. |
| Cron timeout | `timeoutSeconds: 120` in `jobs.json`. 60 too short, 180 causes zombie runs. |
| GitHub push | No SSH key or credential helper on VPS. Use PAT: `git remote set-url origin https://<token>@github.com/zsoist/cldw_Setup.git`, push, reset URL back. |
| Pull with stash | `git stash --include-untracked` before pull, then `git stash drop` after (don't pop — stash may be old versions). |

---

### Latest pass (2026-02-26, Sentinel empty-response hardening + Telegram usage footer)

- `sentinel/sentinel.py`
  - Gemini response extraction hardened: now reads SDK fallback `response.text` when candidate parts are sparse.
  - empty-response path now returns a deterministic user message from the Google loop (instead of bubbling exception), which avoids silent failures and reduces fallback churn.
- `sentinel/telegram_handler.py`
  - all Sentinel command/free-text replies now append a usage footer:
    - `Tokens used: in/out - USD / COP`
    - Brave segment appended only when Brave calls were used.
- `sentinel/config.py`
  - supports `SENTINEL_MAX_TOKENS` (default `768`) and `SENTINEL_USD_TO_COP_RATE` (default `4000`).
- `infrastructure/env.template`, `infrastructure/sync-sentinel-env.sh`
  - include/sync `SENTINEL_MAX_TOKENS` and `SENTINEL_USD_TO_COP_RATE`.
- `sentinel/tests/test_telegram.py`, `sentinel/tests/test_config.py`
  - added coverage for Telegram footer rendering and USD->COP config parsing.
- `openclaw/config/SOUL.md`, `openclaw/skills/ai-daily-brief/SKILL.md`, `openclaw/skills/job-radar/SKILL.md`
  - reinforced no-narration output contract.
  - added mandatory telemetry footer format in user-visible Telegram responses.

### Latest pass (2026-02-26, gateway startup hardening + routing drift cleanup)

- `infrastructure/sync-openclaw-config.sh`
  - adds `gateway.controlUi` generation to runtime config.
  - new env knobs:
    - `OPENCLAW_CONTROL_UI_ALLOWED_ORIGINS` (explicit origin allowlist)
    - `OPENCLAW_CONTROL_UI_HOST_HEADER_FALLBACK` (0/1 fallback toggle)
  - default behavior for non-loopback bind now sets:
    - `gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback=true`
  - this fixes OpenClaw startup failure:
    - `non-loopback Control UI requires gateway.controlUi.allowedOrigins ...`
- `openclaw/openclaw-config.json`
  - template now includes `gateway.controlUi` fallback setting for compatibility with newer OpenClaw runtime validation.
- `infrastructure/env.template`
  - documents new `OPENCLAW_CONTROL_UI_*` variables.
- `infrastructure/vps-rollout-aibrief.sh`
  - now removes stale runtime skill trees:
    - `daily-brief*`
    - `aibrief*`
  - prevents duplicate trigger ownership and non-deterministic `/ai_daily_brief*` routing.
- `infrastructure/aibrief-smoke-test.sh`
  - now fails when deprecated/conflicting `daily-brief*` or `aibrief*` folders exist in runtime skills.
- `openclaw/skills/job-radar/SKILL.md` (new, tracked)
  - version-controls `/job_*` routing previously runtime-only.
  - enforces response discipline (no narration), backend-only retrieval, Brave LLM Context policy, and cost-aware model escalation (Flash default, Pro selective, Sonnet on explicit “think harder”).

Operational validation on VPS (2026-02-26 UTC):
- OpenClaw gateway now starts and stays healthy.
- `health-check.sh`: pass (13/13).
- `aibrief-smoke-test.sh`: pass with no failures (warnings only for expected no-inbound/no-output-yet conditions).

### Latest pass (2026-02-26, crash-safe API cost tracking + rollups)

- `sentinel/cost_tracker.py` (new)
  - append-only event log + atomic summary snapshots.
  - tracks API usage with estimated USD and daily/weekly/monthly/all-time aggregates.
  - provider/model breakdown included.
- `sentinel/sentinel.py`
  - records usage on every Anthropic/Gemini API call in tool loop.
  - records error events when provider calls fail, so failures are visible in cost telemetry.
- `sentinel/config.py`
  - new config/env support:
    - `SENTINEL_COST_TRACKING_ENABLED`
    - `SENTINEL_API_USAGE_LOG_FILE`
    - `SENTINEL_API_COST_SUMMARY_FILE`
    - `SENTINEL_COST_RETENTION_DAYS`
- `infrastructure/update-api-cost-rollup.sh` (new)
  - merges AI Brief run costs (`ai-brief-state.json`) + Sentinel summary into:
    - `/root/.openclaw/workspace/logs/api-cost-rollup.json`
  - outputs daily/weekly/monthly/all-time totals.
- rollout/deploy integration:
  - `infrastructure/vps-rollout-aibrief.sh` now refreshes rollup automatically.
  - `infrastructure/deploy.sh` now refreshes rollup during deployment bootstrap.
- health/smoke visibility:
  - `infrastructure/health-check.sh` checks presence of cost summary and unified rollup.
  - `infrastructure/aibrief-smoke-test.sh` reports unified cost rollup totals when present.
- test coverage:
  - `sentinel/tests/test_cost_tracker.py` added.

### Latest pass (2026-02-26, Job Radar performance/efficiency/cost hardening)

Runtime changes applied on VPS (`/root/job-radar`):

- `backend/app/config.py`
  - added tuning knobs:
    - `brave_discovery_target_jobs` (default `24`)
    - `job_max_age_days` (default `45`)
    - `health_log_interval_minutes` (default `180`)
    - `health_external_check_ttl_seconds` (default `120`)
  - Brave context defaults tightened:
    - `brave_context_max_tokens=3072`
    - `brave_context_max_snippets=20`
- `backend/app/domain/connectors/brave_discovery.py`
  - discovery remains Brave LLM Context-only.
  - per-url context budget reduced (`tokens_per_url=768`, `snippets_per_url=8`).
  - query fan-out now stops early once target candidate count is reached.
  - high-noise domains filtered by host allowlist (`greenhouse.io`, `lever.co`, `workable.com`).
- `backend/app/domain/ingestion/pipeline.py`
  - stale job filter added: skips insert/scoring when `posted_at` exceeds `job_max_age_days`.
  - run summary now includes `stale_filtered`.
  - scoring call reduced to exact new-job count (`limit=totals["new"]`) instead of overfetching.
- `backend/app/domain/health/checker.py`
  - external checks (Brave/Anthropic/Telegram/OpenClaw) now cached with TTL to reduce repeated API spend.
  - cache marker (`"cached": true`) included in responses when applicable.
  - added `reset_health_check_cache()` for deterministic testing/debugging.
- `backend/app/scheduler.py`
  - health-log schedule now configurable (`health_log_interval_minutes`, default every 3h).
- `backend/tests/integration/test_health_checks.py`
  - cache reset fixture added so mocks are deterministic under cached health checks.

Data hygiene applied on VPS:
- removed legacy non-Brave source rows (`remoteok_rss`, `hn_whoshiring`) from Job Radar DB.
- removed old stale rows (`posted_at` older than 45 days).
- removed non-ATS rows (non Greenhouse/Lever/Workable URLs) to improve feed quality.

Operational state after rollout:
- `job-radar-api` healthy, Brave LLM Context checks `OK`.
- ingestion logs show:
  - `brave_only: true`
  - `connectors: ["brave_discovery"]`
  - `target_reached` and `stale_filtered` counters active.

Important deployment note:
- `/root/job-radar` is currently runtime-managed on VPS and **not** part of this git repository tree.
- GitHub repo now documents the production tuning profile and troubleshooting, but backend code sync for Job Radar remains a VPS operation.

### Latest pass (2026-02-23, stale-session narration reset hardening)

- `openclaw/config/SOUL.md`
  - tightened output contract:
    - no internal status commentary in normal responses,
    - one-message execution rule (no "starting/checking/progress" preambles).
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - response discipline now explicitly forbids transitional "starting/checking" messages; final-result-only output.
- alias skills now enforce output-only behavior consistently:
  - `openclaw/skills/ai-daily-brief-morning/SKILL.md`
  - `openclaw/skills/ai-daily-brief-builder/SKILL.md`
  - `openclaw/skills/ai-daily-brief-watchlist/SKILL.md`
  - `openclaw/skills/ai-daily-brief-status/SKILL.md`
- `openclaw/openclaw-config.json`
  - explicit compaction mode set to `safeguard` in defaults to keep long chats from drifting/noising outputs.
  - explicit `thinkingDefault=off` and `verboseDefault=off` to prevent Gemini thinking blocks from leaking as Telegram-visible `Reasoning:` preambles.
- new operational reset utility:
  - `infrastructure/reset-openclaw-telegram-sessions.sh`
  - backs up non-probe session logs, clears `/root/.openclaw/agents/main/sessions/sessions.json` to `{}`, restarts gateway.
- docs updated:
  - `docs/TROUBLESHOOTING.md` and `README.md` now include the session-reset remediation step for stale `Reasoning:`/narration leakage.

### Latest pass (2026-02-23, AI brief response-discipline + natural-language intent normalization)

- `openclaw/config/SOUL.md`
  - enforces no internal narration/chain-of-thought in user-visible replies.
  - adds natural-language AI brief normalization rules:
    - "top ai news of the month/week/12h" -> canonical `/ai_daily_brief top5 ...`
    - "ai daily brief evening/morning" -> canonical mode commands.
  - requires direct execution after normalization (no pre-execution commentary).
- `openclaw/config/AGENTS.md`
  - AI Brief trigger phrases expanded with "top ai news"/"top ai stories".
  - command safety section now explicitly maps natural-language AI brief requests to canonical command forms.
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - adds mandatory response-discipline section:
    - output-only responses (or one concise clarifying question),
    - no `Reasoning:`/pipeline narration,
    - deterministic one-line mode prompt when `/ai_daily_brief` is mode-less,
    - direct execution for clear natural-language intents.
- `openclaw/skills/ai-daily-brief-top5/SKILL.md` and `openclaw/skills/ai-daily-brief-evening/SKILL.md`
  - alias behavior now explicitly forbids internal process narration in user-visible output.

### Latest pass (2026-02-23, stale running-state reconciliation for AI Daily Brief)

- `infrastructure/reconcile-ai-brief-state.sh` (new)
  - detects `last_run.status=running` stale locks in `/root/.openclaw/workspace/logs/ai-brief-state.json`.
  - stale condition: `started_at` missing/invalid OR age >= 900 seconds.
  - auto-finalizes stale runs as `failed` with `finished_at` and explicit interruption error text.
  - supports non-destructive preview mode via `DRY_RUN=1`.
- `infrastructure/vps-rollout-aibrief.sh`
  - now invokes reconcile script after state merge so stale locks are cleared during rollout automatically.
- `infrastructure/deploy.sh`
  - now invokes reconcile script during full deploy flow after state merge.
- `infrastructure/aibrief-smoke-test.sh`
  - now checks for stale `running` state and fails with a targeted remediation command when detected.
- `openclaw/skills/ai-daily-brief/SKILL.md`
  - pipeline step 0 now includes mandatory stale-lock recovery behavior before writing a new run.
  - active runs younger than 900s are treated as in-progress and should not be overwritten.
- alias skills (`morning`, `evening`, `top5`, `builder`, `watchlist`, `status`)
  - now reference canonical stale-lock handling expectations for consistency across `/ai_daily_brief_*` commands.

### Latest pass (2026-02-23, cross-chat narration suppression + session optimization)

- `openclaw/config/SOUL.md`
  - strengthened global response policy:
    - no progress/pre-execution chatter in normal chats,
    - no user-visible tool-step narration,
    - no `Reasoning:` section leakage.
- `openclaw/openclaw-config.json`
  - set `agents.defaults.contextTokens=262144` to cap long-lived session context and reduce drift/token waste.
- VPS runtime remediation:
  - pruned existing Telegram session history keys (`agent:main:telegram:*`) from `sessions.json` with backup and session-file rotation.
  - restarted gateway after prune so new Telegram chats start from clean context under current SOUL/skill rules.

### Latest pass (2026-02-23, Telegram interactive channel sender-compatibility)

- `infrastructure/sync-openclaw-config.sh`
  - added env-controlled Telegram command toggles:
    - `OPENCLAW_TELEGRAM_NATIVE_COMMANDS` (default `1`)
    - `OPENCLAW_TELEGRAM_NATIVE_SKILLS` (default `1`, forced `0` when native commands are disabled)
  - added interactive chat sender-compatibility switch:
    - `OPENCLAW_TELEGRAM_INTERACTIVE_ALLOW_ANY_SENDER=1`
    - when enabled, each chat in `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` gets `groups.<chat>.allowFrom=["*"]` with `requireMention=false`.
- `infrastructure/env.template`
  - documents the new Telegram compatibility/toggle vars.
- `infrastructure/aibrief-smoke-test.sh`
  - native command registration check is now conditional:
    - validates `/getMyCommands` only when runtime `channels.telegram.commands.native=true`
    - reports pass for intentional text-command mode when native commands are disabled.
- Docs refreshed:
  - `openclaw/config/CHANNELS.md`
  - `docs/TROUBLESHOOTING.md`
  - `docs/DEPLOYMENT.md`
  - `README.md`
  - added explicit remediation path for Telegram channel/anonymous sender contexts.

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
  - Schema evolved to v5: includes `history[]`, `feedback[]`, `cost_estimate` in `last_run`, `last_probe_at` in `providers.brave_llm_context`, plus Brave request controls (`request_method`, `threshold_by_mode`, `query_constraints`, `min_inter_query_delay_seconds`).
- `openclaw/config/HEARTBEAT.md`
  - Task 11: Brave provider health probe every 6h (08:00/14:00/20:00 COT).
  - State rules: added cost_estimate, history, last_probe_at, story archive writes after each successful run.
- `openclaw/config/CRON.md`
  - Added Job 15: Brave Provider Health Probe (every 6h, Haiku, state-only mutation).
  - Updated Job 14 format note to include YYYY-MM-DD dates and Technical Details.
- `openclaw/config/AGENTS.md`
  - Updated AI Brief Editor input format with all new commands and model routing for lightweight modes.
- `README.md`
  - Updated AI Daily Brief section with all new commands, state schema v5, story archive, Brave probe, channel setup pointer.
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
- `infrastructure/reconcile-ai-brief-state.sh`
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

### From 2026-02-26 Job Radar + AI Daily Brief audit
1. **Confirm AI brief cron self-heals** — next run at 2026-02-27 12:10 UTC. After run, verify `lastRunStatus: "success"` and `consecutiveErrors: 0` in `jobs.json`, and `last_run.status: "completed"` in `ai-brief-state.json`.
2. **Monitor ai-brief-state.json for future corruption** — the JSON corruption pattern (cron timeout mid-write) will recur if the brief ever exceeds 120s again. If it does, increase `timeoutSeconds` incrementally (try 150). The reconcile script handles stale locks; the JSON fix requires manual Python edit.
3. **Job Radar PM digest** — PM digest at 23:00 UTC (18:00 COT) not directly verified in this session (no log review for it). Verify delivery in channel after the next PM digest window.

### From 2026-02-26 pass (VPS sync + config hardening)
1. **Migrate Sentinel to `google.genai` SDK** — `sentinel.py` uses the deprecated `google.generativeai` package. The FutureWarning appears on every Sentinel startup. Migration requires updating imports and API call patterns in `sentinel.py`. Not urgent (still works), but should be done before the package is removed.
   ```bash
   # current deprecation warning:
   # "All support for the google.generativeai package has ended."
   # "Please switch to the google.genai package"
   ```
2. **Configure GitHub credentials on VPS** — currently push requires a manually-supplied PAT each session. Set up SSH key or a stored credential helper to automate this.
3. **Verify next cron run** — next `Daily Brief Top5` run is scheduled at `nextRunAtMs: 1772194200000` (2026-02-28 12:10 UTC). With `timeoutSeconds: 120` it should succeed. Confirm in `ai-brief-state.json` after the run.
4. **Clear consecutive error count** — `consecutiveErrors: 2` left over from the 60s timeout failures. Will auto-clear on next successful run.

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
8. **Merge latest state schema into runtime:**
   - Run `infrastructure/merge-ai-brief-state.sh` to align runtime state with the current template (v5) without overwriting existing `last_run` / `watchlist` data.

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
