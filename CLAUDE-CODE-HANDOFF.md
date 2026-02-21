# Claude Code Handoff: OpenClaw + Sentinel — Current State

> **For the next Claude Code session.** This document describes the current state of the project, what has been built, what remains, and how to pick up where this session left off. Read fully before making changes.
>
> **Last updated:** 2026-02-21  
> **Branch:** `claude/openclaw-optimization-readme-f9ha4`  
> **Latest commit:** `14f1296` (`fix: harden deployment, sentinel startup, and command safety`)

---

## What This Project Is

A two-layer AI assistant system on a **Hetzner CPX22 VPS** (3 vCPU, 4GB RAM, 80GB NVMe, ~$8/mo):

1. **OpenClaw Gateway** — Multi-agent personal AI running 24/7 in Docker. Two agent profiles (`main` for personal, `work` for professional), accessed via Telegram. Handles research, scheduling, task management, daily briefings, and job search support.

2. **Sentinel** — Custom Python sysadmin bot (Anthropic SDK + tool_use pattern). Manages the VPS: Docker containers, system monitoring, security audits, backups. Separate Telegram bot. Strict command whitelist, deny-by-default.

### Key Architecture Decisions Already Made
- **CPX22 over CPX32** — OpenClaw is I/O bound (API calls), not compute bound
- **Haiku 4.5 as default** — Sonnet escalation only for research/code, Opus manual only
- **Loopback gateway** — No public exposure, SSH tunnel only
- **55-min heartbeat** — Aligns with Anthropic's 60-min prompt cache TTL
- **Multi-agent** — Main (personal) + Work (professional, sandboxed)
- **Target budget** — $18-33/month total (VPS + API)

---

## What Has Been Built (Complete Inventory)

### OpenClaw Configuration (12 config files)

| File | Purpose | Status |
|------|---------|--------|
| `openclaw/config/SOUL.md` | Orchestrator identity, delegation protocol, sub-agent spawning | Done |
| `openclaw/config/USER.md` | Daniel's profile, timezone, preferences | Done |
| `openclaw/config/AGENTS.md` | Sub-agent registry (Researcher, Chief of Staff, Job Search, Academic) + model routing | Done |
| `openclaw/config/TOOLS.md` | Tool permissions, operating rules (change mgmt, read/notify-before-act, deep research opt-in, secret handling) | Done |
| `openclaw/config/HEARTBEAT.md` | 55-min cycle, silent hours, EOD log, weekly review | Done |
| `openclaw/config/MEMORY.md` | Persistent preferences, SOPs, daily log system with growth rules | Done |
| `openclaw/config/IDENTITY.md` | Persona tone (direct, no emojis, no corporate jargon) | Done |
| `openclaw/config/BOOTSTRAP.md` | First-run behavior (retires after setup) | Done |
| `openclaw/config/BOOT.md` | Startup health checks (runs every boot) | Done |
| `openclaw/config/CRON.md` | 10 scheduled jobs (5 personal, 5 business) with full specs | Done |
| `openclaw/config/CHANNELS.md` | Channel security policy (Telegram DM only, no groups, allowlist) | Done |
| `openclaw/config/SANDBOX.md` | Sandbox policy (agent-scope for work, no elevated exec) | Done |

### Work Agent (5 files)

| File | Purpose | Status |
|------|---------|--------|
| `openclaw/agents/work/SOUL.md` | Professional scope only, stricter rules, out-of-scope routing | Done |
| `openclaw/agents/work/TOOLS.md` | Restricted: no shell, no personal workspace, sandbox enforced | Done |
| `openclaw/agents/work/USER.md` | Work-context profile (Dialectica, job search) | Done |
| `openclaw/agents/work/MEMORY.md` | Work-specific memory, isolated from main | Done |
| `openclaw/agents/work/HEARTBEAT.md` | Work hours only (08:00-20:00), max 3 tool calls | Done |

### Workspace Content (Runtime)

| Directory | Content | Status |
|-----------|---------|--------|
| `openclaw/workspace/personal/` | goals.md, routines.md, projects/ | Done |
| `openclaw/workspace/business/` | goals-okrs.md, operating-rules.md, projects/active\|archived/ | Done |
| `openclaw/workspace/outputs/` | summaries/, reports/, drafts/, exports/ | Done (empty dirs) |
| `openclaw/workspace/logs/` | change-log.md, cron-job-results.md | Done |

### Skills (3 skills)

| Skill | Model | Trigger | Status |
|-------|-------|---------|--------|
| `daily-briefing` | Haiku | Scheduled 07:00 daily | Done |
| `research-assistant` | Sonnet | On-demand ("research", "deep dive") | Done |
| `task-tracker` | Haiku | Triggered ("add task", "remind me") | Done |

### Gateway Config

| File | Key Settings | Status |
|------|-------------|--------|
| `openclaw/openclaw-config.json` | Multi-agent profiles (main + work), agent-scope sandbox for work, loopback bind, 55-min heartbeat, Telegram DM only (no groups), security defaults | Done |

### Sentinel (Python Bot)

| File | Purpose | Status |
|------|---------|--------|
| `sentinel/sentinel.py` | Agentic loop, 5-iteration cap, conversation history (20 msg) | Done |
| `sentinel/tools.py` | 8 tools, argument-aware command validation + blocklist, deny-by-default | Done |
| `sentinel/config.py` | Dataclass config with validation | Done |
| `sentinel/telegram_handler.py` | Telegram interface, user ID auth, 5 command handlers | Done |
| `sentinel/requirements.txt` | Python dependencies | Done |
| `sentinel/sentinel.service` | systemd unit file | Done |
| `sentinel/tests/` | conftest.py, test_tools.py, test_telegram.py — all mocked | Done |

### Infrastructure

| File | Purpose | Status |
|------|---------|--------|
| `infrastructure/Dockerfile` | node:20-slim, non-root user, pinned OpenClaw ref build | Done |
| `infrastructure/docker-compose.yml` | CPX22-tuned limits (2 CPU, 2.5GB), loopback port, healthcheck, build arg pin | Done |
| `infrastructure/env.template` | All secret placeholders + `OPENCLAW_REF` pin | Done |
| `infrastructure/deploy.sh` | One-shot VPS deployment with pinned upstream checkout and config copy fixes | Done |
| `infrastructure/secure.sh` | UFW + fail2ban + SSH hardening | Done |
| `infrastructure/backup.sh` | 7-day rotation, excludes .env/.pem/.key | Done |
| `infrastructure/restore.sh` | Interactive restore + archive path safety validation | Done |
| `infrastructure/health-check.sh` | 8-point verification (aggregate reporting fixed) | Done |
| `infrastructure/ssh-config-snippet` | Mac SSH config with tunnel | Done |

### Documentation

| File | Purpose | Status |
|------|---------|--------|
| `docs/DEPLOYMENT.md` | Step-by-step deployment guide | Done |
| `docs/COST-MANAGEMENT.md` | Budget tracking, token optimization | Done |
| `docs/TROUBLESHOOTING.md` | Common issues + recovery | Done |
| `docs/PHASE3-CHECKLIST.md` | Go-live verification | Done |
| `docs/setup/model-routing-policy.md` | 6-tier routing matrix | Done |
| `docs/setup/performance-tuning.md` | API cost + responsiveness tuning | Done |
| `docs/security/access-boundaries.md` | Agent/channel access matrix | Done |
| `docs/security/openclaw-hardening.md` | Gateway security hardening (DM scope, plugins, patches) | Done |
| `docs/playbooks/` | 4 playbooks (daily planning, weekly review, meeting prep, decision log) | Done |
| `docs/templates/` | 3 templates (research summary, brief, SOP) | Done |
| `docs/research/job-search-automation.md` | Job search capabilities + implementation plan | Done |

---

## Session Update (2026-02-21)

The following critical issues were fixed in commit `14f1296`:

1. **Sentinel startup fixed**
   - `sentinel.service` now starts `telegram_handler.py` (actual runtime entrypoint)
   - Added systemd `EnvironmentFile` support for `/root/openclaw/.env` and optional `/opt/sentinel/.env`

2. **Environment loading fixed**
   - `sentinel/config.py` now loads env vars from common deployment paths (`/root/openclaw/.env`, `/opt/sentinel/.env`, local `.env`)

3. **Workspace path consistency fixed**
   - `openclaw/openclaw-config.json` profile workspaces now align with seeded folders:
     - main -> `/home/node/.openclaw/workspace/personal`
     - work -> `/home/node/.openclaw/workspace/business`

4. **Command execution hardening**
   - Replaced prefix-only command checks with argument-aware validators in `sentinel/tools.py`
   - Removed broad file-read vectors (`tail/head/wc` on arbitrary paths)
   - Added tests covering blocked sensitive file reads and curl egress restrictions

5. **Reproducible deployment hardening**
   - Introduced `OPENCLAW_REF` pinning in deploy flow, Dockerfile, compose, and env template
   - Ensured `openclaw-config.json` is copied into Docker build context before `docker compose build`

6. **Operations safety hardening**
   - `health-check.sh` now reports all checks without fail-fast behavior
   - `restore.sh` validates archive paths before extraction

Validation completed in-session:
- `pytest` (Sentinel): **24 passed**
- `bash -n` checks for all infra scripts: **pass**
- Python compile + JSON config parse: **pass**

---

## What Remains (Not Yet Done)

### Deployment
1. **First real deployment to VPS** — Daniel has a Hetzner account but hasn't provisioned yet
2. **Fill .env with real secrets** — Telegram bot tokens, Anthropic API key, gateway token
3. **Keep or update `OPENCLAW_REF` intentionally** — only change when ready to test an upstream OpenClaw upgrade

### Post-Deployment
4. **Telegram bot setup** — Create 2 bots via @BotFather, get tokens, get user ID
5. **First-boot test** — BOOTSTRAP.md behavior, then transition to normal operation
6. **Cron job activation** — The 10 jobs in CRON.md need to be created via OpenClaw CLI/TUI
7. **Calendar integration** — Not yet connected (several cron jobs reference it)

### Future (Not Urgent)
8. **Additional channels** — WhatsApp, Discord disabled, add only if needed
9. **Custom skills** — Build more as patterns emerge
10. **Weekly memory curation** — Review and prune MEMORY.md growth

---

## Key Files to Understand

If you're picking up this project, read these first:

1. **`README.md`** — Full architecture, optimization strategy, security model
2. **`openclaw/config/SOUL.md`** — Agent behavior (sent with every API request, <500 words)
3. **`openclaw/config/AGENTS.md`** — Sub-agent registry and model routing rules
4. **`openclaw/config/CRON.md`** — All 10 scheduled jobs with full specs
5. **`openclaw/openclaw-config.json`** — Gateway config with multi-agent profiles
6. **`sentinel/tools.py`** — Tool definitions + whitelist/blocklist (the security core)
7. **`docs/security/access-boundaries.md`** — Who can access what

---

## Do NOT Change Without Good Reason

| Item | Why |
|------|-----|
| SOUL.md word count (<500) | Sent with every request — every word costs tokens at scale |
| Heartbeat interval (55 min) | Cache-aligned with Anthropic's 60-min TTL |
| Default model (Haiku) | 80%+ of tasks are routine — Sonnet/Opus only when needed |
| Loopback gateway bind | SSH tunnel is the access model — no public exposure |
| Sandbox policy (no elevated exec) | Core security invariant |
| Sentinel whitelist approach | Deny-by-default is the right posture |
| Backup secret exclusion | .env, .pem, .key must never be in tarballs |

---

## Project Evolution Log

This project was built iteratively across multiple sessions:

1. **Original spec** — Two-bot system (OpenClaw + Sentinel) on Hetzner VPS
2. **CPX32 → CPX22** — Downsized after analysis showed I/O-bound workload
3. **Guide 1 (Orchestrator)** — Transformed SOUL.md into multi-agent orchestrator with 4 sub-agents, added TOOLS.md, daily log system, weekly reviews
4. **Guide 2 (Gateway Mechanics)** — Added multi-agent mode (main + work), bootstrap/identity files, sandbox policy, channel security, work agent workspace
5. **Guide 3 (Operational Playbook)** — Added workspace content tree (personal/, business/, outputs/, logs/), 10 cron jobs, BOOT.md, model routing policy doc, playbooks/templates, operating rules in TOOLS.md

Each guide refined the system without breaking prior work. The README was updated after each pass.
