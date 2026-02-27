# Claude Code Handoff: OpenClaw + Sentinel

> For the next LLM session. Last updated: 2026-02-27.
>
> **Start here:** Read `README.md` for architecture overview, `ARCHITECTURE.md` for codebase navigation.

---

## System Overview

A dual-bot AI system on a Hetzner CPX22 VPS (Ubuntu 24.04, 3 vCPU, 4GB RAM).

### Tenant-Landlord Architecture

| Component | Role | Runtime | Primary Model |
|-----------|------|---------|---------------|
| **OpenClaw** (tenant) | User-facing AI: research, briefs, job search, scheduling, image/video/audio | Docker container (`openclaw-openclaw-gateway-1`) | Gemini 2.5 Flash (default), Pro (complex tasks) |
| **Sentinel** (landlord) | Infrastructure sysadmin: Docker mgmt, system monitoring, security, backups, cost tracking | systemd service (`sentinel.service`) | Gemini 2.5 Flash only |
| **Job Radar** | Automated job discovery + digests | Docker containers (`job-radar-api` + `job-radar-db`) | Gemini 2.5 Flash |

**Key boundary:** Sentinel does NOT handle AI briefs, research, image generation, or user tasks. That is OpenClaw's domain. Sentinel monitors the VPS, manages Docker, and tracks costs.

### Model Policy

- **Default:** `google/gemini-2.5-flash` — everything starts here
- **Escalation:** `google/gemini-2.5-pro` — AI brief synthesis, complex research
- **Manual only:** `anthropic/claude-sonnet-4-6` — explicit "think harder" requests
- **Manual only:** `anthropic/claude-opus-4-6` — explicit `/model opus` trigger
- **BANNED:** Haiku — all alias paths redirect to Sonnet/Flash. Never used in production.
- **Auto-fallback:** DISABLED. If Gemini fails, retry once then error. No silent Anthropic switch.

---

## Current State (2026-02-27)

All services healthy. Branch: `main`. Recent work:

1. **Telegram reliability pass** — Complete rewrite of `telegram_handler.py`: Markdown v1 escaping, crash-safe typing, newline-boundary chunking, None guard, error handling hardening. Thread-safe conversation history via `_persist_history()`.
2. **Gemini best practices** — XML-structured system prompts, `temperature: 0.2` for Sentinel (deterministic sysadmin), 60s API timeouts, media understanding enabled in OpenClaw.
3. **Cost optimization** — Pricing table corrected (Flash was 3x underreported), memory leak fix, pruning throttle, dead fallback code removed.
4. **Model optimization** — Haiku purged from all active code paths, auto-fallback disabled, all Anthropic usage is manual-only.
5. **Expert Network Brief** — Expert network competitive intelligence (8 competitors, Flash only, 2x daily).

---

## Critical File Paths

### Sentinel (landlord — `/opt/sentinel/` on VPS, `sentinel/` in repo)

| File | Purpose |
|------|---------|
| `sentinel.py` | Agentic loop, system prompt, model routing, conversation mgmt |
| `telegram_handler.py` | Telegram interface, commands, Markdown escaping, chunking |
| `config.py` | Dataclass config from env vars |
| `cost_tracker.py` | Crash-safe API cost tracking + aggregation |
| `tools.py` | 9 tools + whitelist/blocklist security |
| `tests/` | 65+ tests (config, tools, telegram, cost, provider) |

### OpenClaw (tenant — `/root/.openclaw/` live, `openclaw/` in repo)

| File | Purpose |
|------|---------|
| `openclaw-config.json` | Gateway runtime config (model routing, media, compaction) |
| `config/SOUL.md` | Orchestrator identity (~800 tokens, sent with every request) |
| `config/AGENTS.md` | Sub-agent registry + model routing policy |
| `config/TOOLS.md` | Tool policy + permissions + media policies |
| `config/HEARTBEAT.md` | 90-min interval, active hours, minimal tasks |
| `skills/` | Skill definitions (AI brief, ENB, job-radar, research, etc.) |
| `workspace/logs/ai-brief-state.json` | AI brief run state (check for zombie locks) |

### Infrastructure

| File | Purpose |
|------|---------|
| `infrastructure/docker-compose.yml` | Resource limits, env defaults |
| `infrastructure/ocdash.sh` | Mac convenience script: SSH tunnel + dashboard URL + browser |
| `infrastructure/ssh-config-snippet` | SSH config for Mac (`Host openclaw` → VPS) |
| `infrastructure/aibrief-smoke-test.sh` | AI brief health + token smoke test |
| `/etc/sentinel/sentinel.env` | Sentinel runtime env vars |
| `/root/openclaw/docker-compose.yml` | Live Docker compose (AIDB_BRAVE_* vars) |

---

## File Ownership Rules

**CRITICAL:** Editing files resets ownership to `root:root`. Always fix after:

```bash
# After editing any Sentinel file:
chown sentinel:sentinel /opt/sentinel/*.py

# After editing any OpenClaw config:
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
```

---

## Deployment Checklist

```bash
# 1. Run tests
cd /root/openclaw-project/sentinel && python3 -m pytest tests/ -v

# 2. Deploy Sentinel
cp sentinel/sentinel.py sentinel/telegram_handler.py /opt/sentinel/
chown sentinel:sentinel /opt/sentinel/*.py
systemctl restart sentinel && systemctl status sentinel

# 3. Deploy OpenClaw config changes
cp openclaw/openclaw-config.json /root/.openclaw/openclaw.json
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1

# 4. Verify
systemctl status sentinel --no-pager
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

---

## Cron Jobs (3 total)

| # | Job | Schedule (UTC) | COT | Model |
|---|-----|---------------|-----|-------|
| 1 | AI Daily Brief Top5 | `10 12 * * *` | 07:10 | Gemini Pro |
| 2 | Expert Network Brief AM | `0 12 * * *` | 07:00 | Gemini Flash |
| 3 | Expert Network Brief PM | `0 23 * * *` | 18:00 | Gemini Flash |

Session: isolated. Delivery: Telegram channel `-1003826801947`. Max concurrent: 1.

---

## Known Gotchas

| Issue | Detail |
|-------|--------|
| `google.generativeai` deprecation | FutureWarning on every Sentinel start. Migrate to `google.genai` SDK when stable. |
| Config reload silent success | `docker kill --signal=SIGUSR1` logs nothing on success, only errors. |
| Compaction modes | Only `"default"` and `"safeguard"` are valid. `"aggressive"` causes silent rejection. |
| `heartbeatModel` | NOT a valid key. Use `agents.defaults.heartbeat.model` instead. |
| Zombie AI brief runs | Check `ai-brief-state.json` for `last_run.status="running"` stuck state. |
| Job Radar health checks | Every 30s is normal (Docker health check), not an error. |
| Telegram long-poll 10s | This is NOT an LLM call — just HTTP to Telegram. Zero token cost at idle. |
| SKILL.md `model:` field | Prompt hint only, NOT gateway-enforced. Cron `jobs.json` model IS enforced. |
| Session constraint | Message tool is constrained to session target. Cron = unconstrained = delivers to channel. |

---

## Cost Targets

| Component | Monthly |
|-----------|---------|
| Hetzner CPX22 | ~$8 |
| LLM APIs (Gemini-first) | $6-15 |
| **Total** | **$14-23** |

Daily API budget: <$5. Sentinel zero-cost commands (`/status`, `/cost`, etc.) bypass LLM entirely.

---

## What NOT to Change

- Do not enable auto-fallback to Anthropic (cost explosion risk)
- Do not use Haiku for anything (banned — all aliases redirect)
- Do not set compaction to `"aggressive"` (invalid, causes silent config rejection)
- Do not add `heartbeatModel` key (use `agents.defaults.heartbeat.model`)
- Do not push secrets to git (`.env` is in `.gitignore`)
- Do not skip `chown` after editing config files
