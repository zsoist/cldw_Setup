# Architecture Index
> LLM-optimized codebase map for zsoist/cldw_Setup
> Last updated: 2026-03-01
> Read this file FIRST in any new session.

## System Overview

- VPS: Hetzner CPX22, Ubuntu 24.04, 3 vCPU, 4 GB RAM, 80 GB disk
- 4 services: OpenClaw (Docker), Sentinel (systemd), Job Radar API (Docker), Job Radar DB (Docker)
- Repo: `/root/openclaw-project/` -- config templates, scripts, Sentinel source
- Live OpenClaw: `/root/.openclaw/` -- runtime config, skills, workspace (NOT in repo)
- Live Sentinel: `/opt/sentinel/` -- deployed Python files (NOT in repo, synced from sentinel/)

---

## File Index -- Repository

### Root Files

| File | Purpose |
|------|---------|
| README.md | Human-readable project docs |
| ARCHITECTURE.md | THIS FILE -- LLM codebase index, read first |
| CLAUDE-CODE-HANDOFF.md | Session handoff state |
| .gitignore | .env, venv, __pycache__, backups |

### sentinel/ -- Sysadmin Bot Source

| File | Purpose | Key Values |
|------|---------|------------|
| sentinel.py | Main bot: agentic loop, provider abstraction, token tracking | max_iterations=4, primary: google/gemini-flash |
| telegram_handler.py | Telegram interface, slash commands, auth | Zero-cost: /status /openclaw /security /backup /cost |
| tools.py | 11 tool definitions + whitelist/blocklist security | system_stats, docker_status, docker_restart, docker_logs, run_command, check_security, check_openclaw_health, backup_openclaw, cost_summary, openclaw_cron_status, check_api_spirals |
| config.py | Dataclass config with env var parsing | SENTINEL_MAX_TOKENS=1500, SENTINEL_PROVIDER=google |
| cost_tracker.py | Crash-safe JSONL cost logging + persistent VPS-wide cost cache | /var/log/sentinel/api-usage.jsonl + vps-cost-cache.json |
| requirements.txt | Python deps | google-generativeai, anthropic, python-telegram-bot, psutil |
| sentinel.service | systemd unit file | User=sentinel, Restart=always |

### sentinel/tests/ -- Pytest Suite (mocked, zero API cost)

| File | Purpose |
|------|---------|
| conftest.py | Shared fixtures |
| test_tools.py | Tool execution tests |
| test_telegram.py | Telegram handler tests |
| test_config.py | Config parsing tests |
| test_cost_tracker.py | Cost tracking tests |
| test_provider_fallback.py | Provider fallback tests |

### openclaw/config/ -- Agent Workspace Templates (14 files)

| File | Deploys to | Purpose |
|------|-----------|---------|
| SOUL.md | /root/.openclaw/workspace/SOUL.md | Orchestrator identity, autonomy, tool use, command routing, presentation (~120 lines) |
| AGENTS.md | /root/.openclaw/workspace/AGENTS.md | Sub-agent registry + model routing, behavioral contract |
| TOOLS.md | /root/.openclaw/workspace/TOOLS.md | Tool preference order, efficiency, budget, safety |
| USER.md | /root/.openclaw/workspace/USER.md | Daniel's profile + preferences |
| HEARTBEAT.md | /root/.openclaw/workspace/HEARTBEAT.md | 180m interval, 07:00-23:00 COT, Codex model |
| MEMORY.md | /root/.openclaw/workspace/MEMORY.md | Persistent memory system with daily logs |
| IDENTITY.md | /root/.openclaw/workspace/IDENTITY.md | Persona tone + style |
| CHANNELS.md | /root/.openclaw/workspace/CHANNELS.md | Channel security |
| CRON.md | /root/.openclaw/workspace/CRON.md | 2 cron jobs: AI 12:10 UTC, ENB 12:00 UTC |
| BOOT.md | /root/.openclaw/workspace/BOOT.md | Startup health checks |
| BOOTSTRAP.md | /root/.openclaw/workspace/BOOTSTRAP.md | First-run greeting |
| SANDBOX.md | /root/.openclaw/workspace/SANDBOX.md | Sandbox policy |
| MEDIA.md | /root/.openclaw/workspace/MEDIA.md | Media handling guidelines |

### openclaw/skills/ -- Prompt-Based Skills (NOT executable scripts)

| Skill Directory | Trigger | Model Hint |
|----------------|---------|-----------|
| news-brief/ | /brief, /ai_daily_brief*, /expert_network_brief*, /enb, NL | Codex (~410 lines) |
| job-radar/ | /job_* | Codex |

**CRITICAL: Skills are prompt-based. NEVER exec shell scripts from skill directories -- none exist.**

### openclaw/ -- Other Config Files

| File | Purpose | Notes |
|------|---------|-------|
| openclaw-config.json | Gateway config TEMPLATE (placeholder secrets) | Repo copy of /root/.openclaw/openclaw.json |
| jobs.json | Cron job definitions | 2 jobs: news-brief-ai (Codex, 120s), news-brief-enb (Codex, 120s) |
| docker-compose.yml | OpenClaw Docker Compose | |
| SOUL.md, AGENTS.md, CRON.md | Root-level config (synced to config/ dir) | |

### infrastructure/ -- Deployment & Operations Scripts

| File | Purpose |
|------|---------|
| docker-compose.yml, Dockerfile | Container build |
| deploy.sh, secure.sh | VPS setup |
| backup.sh, restore.sh | Backup/restore |
| health-check.sh | Multi-check system health |
| reload-config.sh | Safe config reload (validates + fixes perms + SIGUSR1) |
| aibrief-smoke-test.sh | Brief health + token + state smoke test |
| Various rollout/sync/reset scripts | |

### docs/ -- Reference Documentation

| Path | Contents |
|------|----------|
| docs/DEPLOYMENT.md | Deployment guide |
| docs/TROUBLESHOOTING.md | Troubleshooting guide |
| docs/COST-MANAGEMENT.md | Cost management guide |
| docs/setup/model-routing-policy.md | Model routing policy |
| docs/setup/performance-tuning.md | Performance tuning guide |
| docs/security/access-boundaries.md | Access boundaries |
| docs/security/openclaw-hardening.md | OpenClaw hardening |
| docs/security/secrets-rotation.md | Secrets rotation |
| docs/playbooks/ | daily-planning, meeting-prep, decision-log-template, personal-weekly-review, ai-daily-brief |
| docs/templates/ | brief-template, research-summary-template, sop-template, ai-daily-brief-template |
| docs/research/ | job-search-automation |

### job-radar/ -- Job Radar Project

| Path | Purpose |
|------|---------|
| docker-compose.v3.yml | Job Radar Docker Compose |
| v3/app/ | FastAPI backend (config.py, main.py, scheduler.py, api/, connectors/, ingestion/, dedup/, enrichment/, scoring/, telegram/) |
| v3/Dockerfile | Container build |
| v3/requirements.txt | Python deps |
| v3/sql/ | DB migrations |
| v3/tests/ | Test suite |

---

## Live System Paths (NOT in repo)

| Path | Purpose | Owner | Notes |
|------|---------|-------|-------|
| /root/.openclaw/openclaw.json | Live gateway config | sentinel:systemd-journal (640) | Edit resets to root:root |
| /root/.openclaw/cron/jobs.json | Live cron jobs (2 jobs) | sentinel:systemd-journal | Both Codex/120s |
| /root/.openclaw/workspace/ | Live workspace (SOUL.md, AGENTS.md, etc.) | sentinel:systemd-journal | Bind-mounted |
| /root/.openclaw/skills/ | Live skills | sentinel:systemd-journal | 2 skills |
| /root/.openclaw/secrets/ | Token files | sentinel:systemd-journal | telegram-default.token |
| /opt/sentinel/*.py | Live Sentinel source | sentinel:sentinel | Synced from repo |
| /etc/sentinel/sentinel.env | Sentinel env vars | root:root (600) | Provider, tokens, etc. |
| /root/openclaw/.env | Docker env vars | root:root (600) | API keys -- NEVER commit |
| /root/openclaw/docker-compose.yml | Live Docker Compose | root:root | |
| /var/log/sentinel/ | Sentinel logs | sentinel:sentinel | api-usage.jsonl, vps-cost-cache.json |
| /root/job-radar/ | Job Radar project | root:root | .env, docker-compose.v3.yml |
| /root/job-radar/v3/app/ | Job Radar FastAPI source | root:root | |

---

## Key Config Values (Source of Truth)

### OpenClaw Gateway (openclaw.json)

| Config | Value | JSON Path |
|--------|-------|-----------|
| Default model | openai-codex/gpt-5.3-codex | agents.defaults.model.primary |
| Fallbacks | ["google/gemini-2.5-flash"] | agents.defaults.model.fallbacks |
| imageModel | openai-codex/gpt-5.3-codex | agents.defaults.imageModel.primary |
| Auth | OAuth (openai-codex:default) | auth.profiles |
| contextTokens | 65536 | agents.defaults.contextTokens |
| contextPruning mode | cache-ttl | agents.defaults.contextPruning.mode |
| contextPruning TTL | 3m | agents.defaults.contextPruning.ttl |
| Compaction | safeguard | agents.defaults.compaction.mode |
| thinkingDefault | off | agents.defaults.thinkingDefault |
| Heartbeat interval | every 180m, Codex | agents.defaults.heartbeat |
| Active hours | 07:00-23:00 COT | agents.defaults.heartbeat.activeHours |
| Session timeout | 300s | agents.defaults.timeoutSeconds |
| maxConcurrent | 2 | agents.defaults.maxConcurrent |
| Sub-agent model | openai-codex/gpt-5.3-codex | agents.defaults.subagents.model |
| Sub-agent timeout | 120s | agents.defaults.subagents.runTimeoutSeconds |
| Sub-agent concurrent | 1 | agents.defaults.subagents.maxConcurrent |
| Brave search | provider: brave | tools.web.search.provider |
| tools.deny | ["browser","canvas","nodes","tts","image","web_fetch"] | tools.deny |

### Cron Jobs (jobs.json)

| Job | Model | Timeout | Schedule |
|-----|-------|---------|----------|
| news-brief-ai | openai-codex/gpt-5.3-codex | 120s | 10 12 * * * UTC (07:10 COT) |
| news-brief-enb | openai-codex/gpt-5.3-codex | 120s | 0 12 * * * UTC (07:00 COT) |

### Sentinel (sentinel.env)

| Config | Value |
|--------|-------|
| Provider | google / gemini-2.5-flash |
| max_tokens | 1500 |
| max_tool_iterations | 4 |
| conversation_ttl | 900s |
| usd_to_cop_rate | 4000 |

### Job Radar

| Config | Value |
|--------|-------|
| API port | 8080 (loopback only) |
| DB | PostgreSQL 16, db=jobradar |

---

## Critical Gotchas

1. **File ownership after Edit**: /root/.openclaw/* -> chown sentinel:systemd-journal; /opt/sentinel/*.py -> chown sentinel:sentinel
2. **compaction.mode**: only "default" or "safeguard" valid -- "aggressive" and "auto" silently rejected
3. **SIGUSR1 reload**: can trigger exit-0 restart -- on-failure:5 won't auto-restart. Safe pattern: `docker compose down && docker compose up -d`
4. **Skills are prompt-based**: NEVER exec shell scripts from skill directories
5. **Gemini proto objects**: use `getattr()`, NOT `.get()` -- proto != dict
6. **openclaw-config.json (repo) is a TEMPLATE** -- real config is /root/.openclaw/openclaw.json
7. **Container uid=999 = sentinel uid=999** -- file permissions must match for bind-mounted paths
8. **Provider fallback (Google<->Anthropic)**: history format incompatible -- must clear conversations dict on fallback
9. **SKILL.md frontmatter model**: NOT gateway-enforced -- only prompt hint. Cron job "model" IS gateway-enforced.
10. **\<think\> tags**: absolute ban -- wastes 20K+ tokens and crashes sessions
11. **Codex thinkingDefault**: "off" (model reasons internally regardless; setting controls API-level reasoning tokens)
12. **Codex behavioral tuning**: bias to action, no clarification questions, no preamble messages (SOUL.md + SKILL.md)
13. **Docker restart policy**: on-failure:5 (prevents restart spirals)

---

## Relationship Map

```
repo sentinel/*.py          --sync-->  /opt/sentinel/*.py               (chown sentinel:sentinel)
repo openclaw/config/*.md   --sync-->  /root/.openclaw/workspace/*.md   (chown sentinel:systemd-journal)
repo openclaw/skills/       --sync-->  /root/.openclaw/skills/          (chown sentinel:systemd-journal)
repo openclaw/openclaw-config.json --render--> /root/.openclaw/openclaw.json (render secrets from .env)
repo openclaw/jobs.json     --sync-->  /root/.openclaw/cron/jobs.json   (chown sentinel:systemd-journal)
repo infrastructure/docker-compose.yml --sync--> /root/openclaw/docker-compose.yml
```

---

## Service Management

| Service | Start/Restart | Logs | Health |
|---------|--------------|------|--------|
| OpenClaw gateway | `docker compose -f /root/openclaw/docker-compose.yml down && docker compose up -d` | `docker logs openclaw-openclaw-gateway-1` | Docker health check |
| Config reload | `reload-config.sh` (validates + fixes perms + SIGUSR1) | docker logs for errors | No success log |
| Sentinel | `systemctl restart sentinel` | `journalctl -u sentinel -f` | `systemctl status sentinel` |
| Job Radar API | `docker compose -f /root/openclaw/docker-compose.yml -f /root/job-radar/docker-compose.v3.yml --project-directory /root/job-radar up -d` | `docker logs job-radar-agent` | `curl localhost:8080/health` |
| Job Radar DB | (same compose as API) | `docker logs job-radar-db` | Internal |
