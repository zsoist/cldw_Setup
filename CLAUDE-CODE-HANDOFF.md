# Claude Code Handoff

> Last updated: 2026-03-02 | Full audit + cost fix + Discord migration prep
>
> **Start here:** Read `README.md` for architecture, this file for deployment state.

---

## Current State

All services healthy. Codex migration complete. Non-essential cron jobs disabled pending Discord migration.

### Active Services

| Service | Status | Notes |
|---------|--------|-------|
| OpenClaw Gateway | Running, healthy | Codex-first, 2 sessions max |
| Sentinel Bot | Running, polling | 12 tools, 104 tests passing |
| Job Radar API | Running, healthy | Scheduler **paused** (all 6 jobs) |
| Job Radar DB | Running, healthy | PostgreSQL 16 |

### Cron Job Status

| Job | Status | Notes |
|-----|--------|-------|
| news-brief-ai | **DISABLED** | `enabled: false` in jobs.json |
| news-brief-enb | **DISABLED** | `enabled: false` in jobs.json |
| JR cleanup | **PAUSED** | Scheduler-level pause |
| JR discovery_sync | **PAUSED** | Scheduler-level pause |
| JR watchlist_sync | **PAUSED** | Scheduler-level pause |
| JR digest_am | **PAUSED** | Scheduler-level pause |
| JR digest_pm | **PAUSED** | Scheduler-level pause |
| JR weekly_report | **PAUSED** | Scheduler-level pause |
| System maintenance (11) | **ACTIVE** | Hourly, daily, weekly, monthly, docker-prune, log-cleanup, backup, disk-scrub, sysstat |
| OpenClaw maintenance (2) | **ACTIVE** | log-cleanup (weekly), backup (daily) |

### Recent Changes (2026-03-02)

**Full Sentinel audit + bug fixes:**
- Fixed `/cost today` permission denied -- root cause: Edit tool resets `.py` + `.pyc` ownership to root:root; sentinel process can't read its own source files
- Fix: added `set_cost_tracker()` module-level pattern -- cost reads now use APICostTracker.get_summary() (thread-safe, in-memory) instead of raw file open
- Fixed HTTP health probe -- was using host `curl` (always returned 000); now uses `container.exec_run()` inside container (returns 200)
- Added `/tasks` zero-cost command for listing all scheduled tasks
- Added `manage_cron` tool for enabling/disabling cron jobs across services
- Sentinel: 12 tools total, 104 tests passing
- Disabled non-essential cron jobs pending Discord migration

### Prior (2026-03-01)

**Codex-first migration** -- switched all OpenClaw models to gpt-5.3-codex (subscription-covered, OAuth).

### Prior (2026-02-28)

**News Brief v4** -- consolidated 9 skills into 1 skill + 1 state file.

---

## Critical File Paths

### Live (on VPS)

| File | Purpose |
|------|---------|
| `/root/.openclaw/openclaw.json` | Gateway runtime config (Codex OAuth, 65536 context) |
| `/root/.openclaw/skills/news-brief/SKILL.md` | News Brief v4 skill (~410 lines) |
| `/root/.openclaw/skills/job-radar/SKILL.md` | Job Radar bridge skill |
| `/root/.openclaw/workspace/logs/news-brief-state.json` | Brief run state |
| `/root/.openclaw/cron/jobs.json` | Cron registry (2 jobs, both DISABLED) |
| `/root/.openclaw/workspace/SOUL.md` | Core personality + routing + Codex behavioral tuning |
| `/root/.openclaw/workspace/AGENTS.md` | Agent registry + behavioral contract |
| `/root/.openclaw/workspace/TOOLS.md` | Tool policy + efficiency rules |
| `/root/.openclaw/workspace/CRON.md` | Cron docs |
| `/opt/sentinel/*.py` | Sentinel source (Flash, separate service) |
| `/etc/sentinel/sentinel.env` | Sentinel env vars (max_tokens=1500) |
| `/root/openclaw/docker-compose.yml` | Docker config |
| `/var/log/sentinel/` | Logs + cost tracking (api-usage.jsonl, api-cost-summary.json, vps-cost-cache.json) |

### Repo (this repo)

| File | Mirrors |
|------|---------|
| `sentinel/*.py` | `/opt/sentinel/*.py` |
| `sentinel/tests/` | Test suite (104 tests) |
| `openclaw/skills/news-brief/SKILL.md` | `/root/.openclaw/skills/news-brief/SKILL.md` |
| `openclaw/skills/job-radar/SKILL.md` | `/root/.openclaw/skills/job-radar/SKILL.md` |
| `openclaw/config/*.md` | `/root/.openclaw/workspace/*.md` |
| `openclaw/jobs.json` | `/root/.openclaw/cron/jobs.json` |
| `openclaw/openclaw-config.json` | `/root/.openclaw/openclaw.json` (sanitized) |

---

## File Ownership Rules

**CRITICAL:** Editing files resets ownership to `root:root`. Always fix after:

```bash
# After editing any OpenClaw config:
chown sentinel:systemd-journal /root/.openclaw/workspace/*.md
chown sentinel:systemd-journal /root/.openclaw/skills/news-brief/SKILL.md
chown sentinel:systemd-journal /root/.openclaw/skills/job-radar/SKILL.md
chown sentinel:systemd-journal /root/.openclaw/cron/jobs.json
chown sentinel:systemd-journal /root/.openclaw/openclaw.json
# Permission: 640 for all

# After editing Sentinel source:
chown sentinel:sentinel /opt/sentinel/*.py
chown sentinel:sentinel /opt/sentinel/__pycache__/*.pyc
# CRITICAL: .pyc files must also be sentinel:sentinel -- root-owned .pyc causes
# PermissionError on module import (640 = rw-r----- means other=---)
```

---

## Cron Jobs

| Job ID | Name | Schedule (COT) | Model | Timeout | Status |
|--------|------|---------------|-------|---------|--------|
| `news-brief-ai` | AI Top 5 | 07:10 daily | Codex | 120s | DISABLED |
| `news-brief-enb` | ENB Top 5 | 07:00 daily | Codex | 120s | DISABLED |

To re-enable: set `enabled: true` in `/root/.openclaw/cron/jobs.json`, fix ownership, reload config.

---

## Deployment

```bash
# 1. Sync config to VPS
cp openclaw/config/*.md /root/.openclaw/workspace/
cp openclaw/skills/news-brief/SKILL.md /root/.openclaw/skills/news-brief/SKILL.md
cp openclaw/skills/job-radar/SKILL.md /root/.openclaw/skills/job-radar/SKILL.md
cp openclaw/jobs.json /root/.openclaw/cron/jobs.json

# 2. Sync Sentinel source
cp sentinel/*.py /opt/sentinel/

# 3. Fix ownership
chown -R sentinel:systemd-journal /root/.openclaw/workspace/ /root/.openclaw/skills/ /root/.openclaw/cron/
chmod 640 /root/.openclaw/workspace/*.md /root/.openclaw/skills/*/SKILL.md /root/.openclaw/cron/jobs.json
chown sentinel:sentinel /opt/sentinel/*.py

# 4. Restart services
systemctl restart sentinel
cd /root/openclaw && docker compose down && docker compose up -d

# 5. Verify
docker inspect openclaw-openclaw-gateway-1 --format='{{.State.Health.Status}}'
systemctl is-active sentinel
```

---

## Re-enabling Cron Jobs

```bash
# OpenClaw briefs (edit jobs.json, set enabled: true)
vi /root/.openclaw/cron/jobs.json
chown sentinel:systemd-journal /root/.openclaw/cron/jobs.json
/root/.openclaw/reload-config.sh

# Job Radar scheduler
curl -X POST http://localhost:8080/api/v1/scheduler/resume
```

---

## Known Gotchas

| Issue | Detail |
|-------|--------|
| SIGUSR1 exit-0 | Can trigger full process restart. Use `docker compose down && up -d` |
| Config reload silent | SIGUSR1 logs nothing on success, only errors |
| Compaction modes | Only `"default"` and `"safeguard"` valid |
| `<think>` tags | Absolute ban in SKILL.md + SOUL.md -- crashes sessions |
| thinkingDefault | Must be `"off"` for Codex |
| `.pyc` ownership | Must be sentinel:sentinel. Root-owned causes PermissionError on import |
| HTTP probe | Must use `exec_run()` inside container. Host curl always gets connection reset |
| Codex clarification | Without anti-clarification prompting, Codex asks preference questions |
| AIDB_BRAVE_* vars | Hard caps: count=5, max_tokens=1024, threshold=strict |

---

## What NOT to Change

- Do not enable auto-fallback to Anthropic (cost explosion, incompatible history format)
- Do not use Haiku (banned)
- Do not set compaction to `"aggressive"` (invalid)
- Do not skip `chown` after editing config files (including `.pyc`)
- Do not push secrets to git
- Do not set thinkingDefault to anything other than `"off"` for Codex
- Do not remove anti-clarification rules from SOUL.md or SKILL.md
- Do not set Docker restart policy to `unless-stopped` (caused 54 restarts in 50 min)

---

## Planned: Discord Migration

Moving primary communications to Discord. Telegram channel repurposed for sharing with friends. Discord is private, sole user.

| Platform | Future Role |
|----------|-------------|
| Discord (private server) | Primary -- OpenClaw chat, ACP threads, Job Radar, News Briefs, Sentinel |
| Telegram Sentinel | Keep -- sysadmin bot (DM) |
| Telegram channel | Repurpose -- sharing with friends |

Key config changes needed: Discord bot token, `channels.discord` in openclaw.json, ACP control-plane, Codex WebSocket transport. Full plan exists in Claude Code session context.
