# Architecture Index
> LLM-optimized codebase map for zsoist/cldw_Setup
> Last updated: 2026-02-28
> Read this file FIRST in any new session.

## System Overview

- VPS: Hetzner CPX22, Ubuntu 24.04
- 4 services: OpenClaw (Docker), Sentinel (systemd), Job Radar API (Docker), Job Radar DB (Docker)
- Repo: `/root/openclaw-project/` -- config templates, scripts, Sentinel source
- Live OpenClaw: `/root/.openclaw/` -- runtime config, skills, workspace (NOT in repo)
- Live Sentinel: `/opt/sentinel/` -- deployed Python files (NOT in repo, synced from sentinel/)

---

## File Index -- Repository

### Root Files

| File | Purpose | Notes |
|------|---------|-------|
| README.md | Human-readable project docs (GitHub) | ~640 lines |
| ARCHITECTURE.md | THIS FILE -- LLM codebase index | Read first |
| CLAUDE-CODE-HANDOFF.md | Session handoff state for Claude Code | ~840 lines, latest pass date, critical rules |
| MODEL_TWEAKING_FOR_OPENCLAW_v1_1_NO_GEMINI_3_1.md | Model tuning reference (no Gemini 3.1) | ~815 lines |
| .gitignore | Git exclusions | .env, venv, __pycache__, backups |

### sentinel/ -- Sysadmin Bot Source

| File | Purpose | Key Values |
|------|---------|------------|
| sentinel.py | Main bot: agentic loop, provider abstraction, token tracking | max_iterations=4, primary: google/gemini-flash, anthropic manual-only (auto-fallback disabled) |
| telegram_handler.py | Telegram interface, slash commands, auth | Zero-cost /status /openclaw /security /backup /cost |
| tools.py | 10 tool definitions + whitelist/blocklist security | system_stats, docker_status, docker_restart, docker_logs, run_command, check_security, check_openclaw_health, backup_openclaw, cost_summary, openclaw_cron_status |
| config.py | Dataclass config with env var parsing | SENTINEL_MAX_TOKENS=768, SENTINEL_PROVIDER=google |
| cost_tracker.py | Crash-safe JSONL cost logging + JSON summary | Writes /var/log/sentinel/api-usage.jsonl + api-cost-summary.json |
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

### openclaw/config/ -- Agent Workspace Templates (12 files)

| File | Purpose | Deploys to |
|------|---------|-----------|
| SOUL.md | Orchestrator identity + rules (~800 tokens) | /root/.openclaw/workspace/SOUL.md |
| AGENTS.md | Sub-agent registry + model routing | /root/.openclaw/workspace/AGENTS.md |
| TOOLS.md | Tool policy + permissions | /root/.openclaw/workspace/TOOLS.md |
| USER.md | Daniel's profile + preferences | /root/.openclaw/workspace/USER.md |
| HEARTBEAT.md | Proactive schedule (180m interval, 07:00-23:00 COT) | /root/.openclaw/workspace/HEARTBEAT.md |
| MEMORY.md | Persistent memory system | /root/.openclaw/workspace/MEMORY.md |
| IDENTITY.md | Persona tone + style | /root/.openclaw/workspace/IDENTITY.md |
| CHANNELS.md | Channel security policy + allowlists | /root/.openclaw/workspace/CHANNELS.md |
| CRON.md | Cron registry (2 jobs: AI 12:10 UTC, ENB 12:00 UTC) | /root/.openclaw/workspace/CRON.md |
| BOOT.md | Startup health checks | /root/.openclaw/workspace/BOOT.md |
| BOOTSTRAP.md | First-run behavior (retires after setup) | /root/.openclaw/workspace/BOOTSTRAP.md |
| SANDBOX.md | Sandbox policy + agent isolation | /root/.openclaw/workspace/SANDBOX.md |

### openclaw/agents/work/ -- Work Agent (sandboxed)

| File | Purpose |
|------|---------|
| SOUL.md | Professional-only scope, stricter rules |
| TOOLS.md | Restricted tool policy |
| USER.md | Work-context profile only |
| MEMORY.md | Work-specific memory (isolated) |
| HEARTBEAT.md | Work-hours schedule (08:00-20:00) |

### openclaw/skills/ -- Prompt-Based Skills (NOT executable scripts)

| Skill Directory | Trigger | Model Hint |
|----------------|---------|-----------|
| news-brief/ | /brief, /ai_daily_brief*, /expert_network_brief*, /enb, NL | Flash |
| job-radar/ | /job_* | Flash |

**CRITICAL: Skills are prompt-based. NEVER exec shell scripts from skill directories -- none exist.**

### openclaw/ -- Other Config Files

| File | Purpose | Notes |
|------|---------|-------|
| openclaw-config.json | Gateway config TEMPLATE (placeholder secrets) | Repo copy of /root/.openclaw/openclaw.json |
| jobs.json | Cron job definitions TEMPLATE | Repo copy of /root/.openclaw/cron/jobs.json |
| docker-compose.yml | OpenClaw Docker Compose (in openclaw/ subdir) | NOT the infra one |
| SOUL.md, AGENTS.md, CHANNELS.md, CRON.md, BOOT.md | Root-level canonical config (synced to config/ dir) | These are the source of truth |

### openclaw/workspace/ -- Runtime Workspace Content Templates

| Subdirectory | Contents |
|-------------|----------|
| personal/ | goals.md, routines.md, projects/.gitkeep |
| business/ | goals-okrs.md, operating-rules.md, projects/active/.gitkeep, projects/archived/.gitkeep |
| outputs/ | summaries/.gitkeep, reports/.gitkeep, drafts/.gitkeep, exports/.gitkeep |
| logs/ | change-log.md, cron-job-results.md, news-brief-state.json |

### infrastructure/ -- Deployment & Operations Scripts

| File | Purpose |
|------|---------|
| Dockerfile | OpenClaw container build (node:22-bookworm + pnpm) |
| docker-compose.yml | Resource limits for CPX22 (2 vCPU, 2560MB for OpenClaw) |
| env.template | Secret placeholders (never committed) |
| deploy.sh | One-shot VPS deployment |
| secure.sh | UFW + fail2ban + SSH hardening |
| sync-sentinel-env.sh | Syncs /root/openclaw/.env to /etc/sentinel/sentinel.env |
| sync-openclaw-config.sh | Renders openclaw.json from .env + template |
| validate-placeholders.sh | Validates required secrets are non-placeholder |
| backup.sh | Automated backup (7-day rotation, no secrets) |
| restore.sh | Interactive restore from backup |
| health-check.sh | Multi-check system health verification |
| aibrief-smoke-test.sh | AI brief health + token + state smoke test |
| vps-rollout-aibrief.sh | Config-only AI brief rollout/update path |
| merge-ai-brief-state.sh | Template to runtime state merge |
| reconcile-ai-brief-state.sh | Auto-close stale running locks |
| set-aibrief-output-channel.sh | Configure AI brief output channel |
| reset-telegram-offset.sh | Reset stale Telegram update offsets |
| reset-openclaw-telegram-sessions.sh | Clear stale runtime sessions |
| update-api-cost-rollup.sh | Merge AI Brief + Sentinel cost data |
| vps-activate-channel-commands.sh | Activate channel command support |
| ssh-config-snippet | Mac SSH config with tunnel |

### docs/ -- Reference Documentation

| Subdirectory/File | Contents |
|-------------------|----------|
| docs/DEPLOYMENT.md | Deployment guide |
| docs/TROUBLESHOOTING.md | Troubleshooting guide |
| docs/COST-MANAGEMENT.md | Cost management guide |
| docs/PHASE3-CHECKLIST.md | Phase 3 completion checklist |
| docs/setup/model-routing-policy.md | Model routing policy |
| docs/setup/performance-tuning.md | Performance tuning guide |
| docs/security/openclaw-hardening.md | OpenClaw hardening |
| docs/security/access-boundaries.md | Access boundaries |
| docs/security/secrets-rotation.md | Secrets rotation |
| docs/playbooks/daily-planning.md | Daily planning playbook |
| docs/playbooks/meeting-prep.md | Meeting prep playbook |
| docs/playbooks/decision-log-template.md | Decision log template |
| docs/playbooks/personal-weekly-review.md | Weekly review playbook |
| docs/playbooks/ai-daily-brief.md | AI daily brief playbook |
| docs/templates/brief-template.md | Brief output template |
| docs/templates/research-summary-template.md | Research summary template |
| docs/templates/sop-template.md | SOP template |
| docs/templates/ai-daily-brief-template.md | AI daily brief template |
| docs/research/job-search-automation.md | Job search automation research |

---

## Live System Paths (NOT in repo)

| Path | Purpose | Owner | Critical Notes |
|------|---------|-------|----------------|
| /root/.openclaw/openclaw.json | Live gateway config | sentinel:systemd-journal (640) | Edit tool resets to root:root -- always chown after |
| /root/.openclaw/cron/jobs.json | Live cron jobs (2 jobs) | sentinel:systemd-journal | AI Brief: Flash/90s, ENB: Flash/90s |
| /root/.openclaw/workspace/ | Live workspace (SOUL.md, AGENTS.md, etc.) | sentinel:systemd-journal | Bind-mounted into container |
| /root/.openclaw/skills/ | Live skills | sentinel:systemd-journal | Synced from repo openclaw/skills/ |
| /root/.openclaw/secrets/ | Token files | sentinel:systemd-journal | telegram-default.token |
| /opt/sentinel/*.py | Live Sentinel source | sentinel:sentinel | Synced from repo sentinel/ |
| /etc/sentinel/sentinel.env | Sentinel env vars | root:root (600) | SENTINEL_PROVIDER, SENTINEL_MAX_TOKENS, etc. |
| /root/openclaw/.env | Docker env vars | root:root (600) | API keys, tokens -- NEVER commit |
| /root/openclaw/docker-compose.yml | Live Docker Compose | root:root | Synced from infrastructure/ |
| /var/log/sentinel/ | Sentinel logs | sentinel:sentinel | api-usage.jsonl, api-cost-summary.json, audit.log |
| /root/job-radar/ | Job Radar project | root:root | .env, docker-compose.job-radar.yml |
| /root/job-radar/backend/app/ | Job Radar FastAPI source | root:root | config.py, domain/, api/ |

---

## Key Config Values (Quick Reference)

| Config | Value | Location |
|--------|-------|----------|
| Default model | google/gemini-2.5-flash | openclaw.json agents.defaults.model.primary |
| Fallbacks | [] (none) | openclaw.json agents.defaults.model.fallbacks |
| imageModel | google/gemini-2.5-flash | openclaw.json agents.defaults.imageModel.primary |
| contextTokens | 32768 | openclaw.json agents.defaults.contextTokens |
| contextPruning mode | cache-ttl | openclaw.json agents.defaults.contextPruning.mode |
| contextPruning TTL | 3m | openclaw.json agents.defaults.contextPruning.ttl |
| Compaction | safeguard | openclaw.json agents.defaults.compaction.mode |
| Heartbeat | every 180m | openclaw.json agents.defaults.heartbeat.every |
| Active hours | 07:00-23:00 COT | openclaw.json agents.defaults.heartbeat.activeHours |
| Session timeout | 300s | openclaw.json agents.defaults.timeoutSeconds |
| Sub-agent model | Flash | openclaw.json agents.defaults.subagents.model |
| AI Brief cron model | Gemini 2.5 Flash | jobs.json [0].payload.model |
| AI Brief cron timeout | 90s | jobs.json [0].payload.timeoutSeconds |
| AI Brief cron schedule | 10 12 * * * UTC (07:10 COT) | jobs.json [0].schedule.expr |
| ENB cron model | Gemini 2.5 Flash | jobs.json [1].payload.model |
| ENB cron schedule | 0 12 * * * UTC (07:00 COT) | jobs.json [1].schedule.expr |
| News Brief state file | news-brief-state.json | workspace/logs/news-brief-state.json |
| Sentinel provider | google | sentinel.env SENTINEL_PROVIDER |
| Sentinel max_tokens | 768 | sentinel.env SENTINEL_MAX_TOKENS |
| Sentinel max_tool_iterations | 4 | sentinel.env SENTINEL_MAX_TOOL_ITERATIONS |
| Brave search | provider: brave | openclaw.json tools.web.search.provider |
| Media understanding | image/video/audio enabled | openclaw.json tools.media.* |
| Image understanding timeout | 60s | openclaw.json tools.media.image.timeoutSeconds |
| Video understanding timeout | 120s | openclaw.json tools.media.video.timeoutSeconds |
| Media concurrency | 2 | openclaw.json tools.media.concurrency |
| Sentinel temperature | 1.0 (Gemini recommended) | sentinel.py generation_config |
| Sentinel API timeout | 60s | sentinel.py request_options.timeout |
| DM policy | allowlist | openclaw.json channels.telegram.dmPolicy |
| thinkingDefault | off | openclaw.json agents.defaults.thinkingDefault |
| verboseDefault | off | openclaw.json agents.defaults.verboseDefault |
| Job Radar llm_standard_model | Flash | job-radar .env (config.py default) |
| Job Radar brave_only | false | job-radar .env JOB_SEARCH_BRAVE_ONLY |
| Job Radar health cache TTL | 10800s (3h) | job-radar .env HEALTH_EXTERNAL_CHECK_TTL_SECONDS |

---

## Critical Gotchas

1. **File ownership after Edit**: /root/.openclaw/* must be chown sentinel:systemd-journal; /opt/sentinel/*.py must be chown sentinel:sentinel. Edit tool runs as root and resets ownership.
2. **compaction.mode**: only "default" or "safeguard" valid -- "aggressive" and "auto" are NOT valid and silently rejected.
3. **SIGUSR1 reload**: `docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1` -- no log on success, errors ARE logged. Always check docker logs after.
4. **Skills are prompt-based**: NEVER exec shell scripts from skill directories. NEVER run /ai_daily_brief as a shell command.
5. **Gemini proto objects**: use `getattr()`, NOT `.get()` -- proto != dict.
6. **openclaw-config.json (repo) is a TEMPLATE** -- real config is /root/.openclaw/openclaw.json. Never deploy the template directly without rendering secrets.
7. **Container uid=999 = sentinel uid=999** -- file permissions must match for bind-mounted paths.
8. **GitHub push**: No SSH key on VPS. Use PAT via `git remote set-url`.
9. **Provider fallback (Google to Anthropic)**: history format is incompatible -- must clear conversations dict on fallback.
10. **SKILL.md frontmatter model**: NOT gateway-enforced -- only a prompt hint. Cron job "model" field IS gateway-enforced.

---

## Relationship Map

```
repo sentinel/*.py          ──sync──>  /opt/sentinel/*.py               (chown sentinel:sentinel)
repo openclaw/config/*.md   ──sync──>  /root/.openclaw/workspace/*.md   (chown sentinel:systemd-journal)
repo openclaw/skills/       ──sync──>  /root/.openclaw/skills/          (chown sentinel:systemd-journal)
repo openclaw/openclaw-config.json ──render──> /root/.openclaw/openclaw.json (render secrets from .env)
repo openclaw/jobs.json     ──sync──>  /root/.openclaw/cron/jobs.json   (chown sentinel:systemd-journal)
repo infrastructure/docker-compose.yml ──sync──> /root/openclaw/docker-compose.yml
```

---

## Service Management Quick Reference

| Service | Start/Restart | Logs | Health Check |
|---------|--------------|------|-------------|
| OpenClaw gateway | `docker compose -f /root/openclaw/docker-compose.yml up -d` | `docker logs openclaw-openclaw-gateway-1` | `infrastructure/health-check.sh` |
| OpenClaw config reload | `docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1` | Check docker logs for errors | No success log |
| Sentinel | `systemctl restart sentinel` | `journalctl -u sentinel -f` | `/opt/sentinel/tools.py` system_stats |
| Job Radar API | `docker compose -f /root/openclaw/docker-compose.yml -f /root/job-radar/docker-compose.job-radar.yml --project-directory /root/job-radar up -d job-radar-api` | `docker logs job-radar-api` | `curl localhost:8080/health` |
| Job Radar DB | (same compose as API) | `docker logs job-radar-db` | Internal only |
