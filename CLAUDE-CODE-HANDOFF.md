# Claude Code Handoff

> Last updated: 2026-03-01 | Codex-first migration complete
>
> **Start here:** Read `README.md` for architecture, this file for deployment state.

---

## Current State

All services healthy. Codex migration complete — all OpenClaw models switched from Flash to `openai-codex/gpt-5.3-codex` (subscription-covered, OAuth).

### Recent Changes (2026-03-01)

**Codex-first migration** — switched all OpenClaw models to gpt-5.3-codex:
- Gateway: model.primary, imageModel, heartbeat.model, subagents.model → Codex
- Auth: OAuth profile (openai-codex:default), subscription-based
- Cron: both jobs → Codex, 120s timeout
- SOUL.md: added autonomy/persistence, tool efficiency, bias-to-action, no-clarification rules
- AGENTS.md: sub-agent behavioral contract, all Codex
- TOOLS.md: tool preference order, parallelism rules
- SKILL.md (news-brief): 20 few-shot examples, 14 anti-patterns, no-clarification constraint
- contextTokens: 65536 (safe with Codex 266K window)
- Behavioral tuning: no preambles, no clarification questions, execute with defaults

### Prior (2026-02-28)

**News Brief v4** — consolidated 9 skills into 1 skill + 1 state file.

---

## Critical File Paths

### Live (on VPS)

| File | Purpose |
|------|---------|
| `/root/.openclaw/openclaw.json` | Gateway runtime config (Codex OAuth, 65536 context) |
| `/root/.openclaw/skills/news-brief/SKILL.md` | News Brief v4 skill (~410 lines) |
| `/root/.openclaw/skills/job-radar/SKILL.md` | Job Radar bridge skill |
| `/root/.openclaw/workspace/logs/news-brief-state.json` | Brief run state |
| `/root/.openclaw/cron/jobs.json` | Cron registry (2 jobs, Codex, 120s) |
| `/root/.openclaw/workspace/SOUL.md` | Core personality + routing + Codex behavioral tuning |
| `/root/.openclaw/workspace/AGENTS.md` | Agent registry + behavioral contract |
| `/root/.openclaw/workspace/TOOLS.md` | Tool policy + efficiency rules |
| `/root/.openclaw/workspace/CRON.md` | Cron docs |
| `/opt/sentinel/*.py` | Sentinel source (Flash, separate service) |
| `/etc/sentinel/sentinel.env` | Sentinel env vars (max_tokens=1500) |
| `/root/openclaw/docker-compose.yml` | Docker config |

### Repo (this repo)

| File | Mirrors |
|------|---------|
| `openclaw/skills/news-brief/SKILL.md` | `/root/.openclaw/skills/news-brief/SKILL.md` |
| `openclaw/skills/job-radar/SKILL.md` | `/root/.openclaw/skills/job-radar/SKILL.md` |
| `openclaw/config/*.md` | `/root/.openclaw/workspace/*.md` |
| `openclaw/jobs.json` | `/root/.openclaw/cron/jobs.json` |
| `openclaw/openclaw-config.json` | `/root/.openclaw/openclaw.json` (sanitized) |
| `sentinel/*.py` | `/opt/sentinel/*.py` |

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
```

---

## Cron Jobs (2 total)

| Job ID | Name | Schedule (UTC) | COT | Model | Timeout |
|--------|------|---------------|-----|-------|---------|
| `news-brief-ai` | AI Top 5 | `10 12 * * *` | 07:10 | Codex | 120s |
| `news-brief-enb` | ENB Top 5 | `0 12 * * *` | 07:00 | Codex | 120s |

---

## Deployment

```bash
# 1. Sync config to VPS
cp openclaw/config/*.md /root/.openclaw/workspace/
cp openclaw/skills/news-brief/SKILL.md /root/.openclaw/skills/news-brief/SKILL.md
cp openclaw/skills/job-radar/SKILL.md /root/.openclaw/skills/job-radar/SKILL.md
cp openclaw/jobs.json /root/.openclaw/cron/jobs.json

# 2. Fix ownership
chown -R sentinel:systemd-journal /root/.openclaw/workspace/ /root/.openclaw/skills/ /root/.openclaw/cron/
chmod 640 /root/.openclaw/workspace/*.md /root/.openclaw/skills/*/SKILL.md /root/.openclaw/cron/jobs.json

# 3. Restart gateway (safe pattern — NOT SIGUSR1 for auth/model changes)
cd /root/openclaw && docker compose down && docker compose up -d

# 4. Verify
docker inspect openclaw-openclaw-gateway-1 --format='{{.State.Health.Status}}'
```

---

## Known Gotchas

| Issue | Detail |
|-------|--------|
| SIGUSR1 exit-0 | Can trigger full process restart → `on-failure:5` won't auto-restart. Use `docker compose down && up -d` |
| `exec elevated` blocked | Gateway blocks `exec` in cron sessions. Use `web_search` for Brave |
| Config reload silent | SIGUSR1 logs nothing on success, only errors |
| Compaction modes | Only `"default"` and `"safeguard"` valid |
| `<think>` tags | Absolute ban in SKILL.md + SOUL.md — crashes sessions |
| thinkingDefault | Must be `"off"` for Codex (model reasons internally regardless) |
| Codex clarification | Without anti-clarification prompting, Codex asks preference questions. Fixed in SOUL.md + SKILL.md |
| AIDB_BRAVE_* vars | Hard caps: count=5, max_tokens=1024, threshold=strict |
| State file overwrite | Both cron jobs write same state file. Last writer wins. Non-critical |

---

## What NOT to Change

- Do not enable auto-fallback to Anthropic (cost explosion, incompatible history format)
- Do not use Haiku (banned)
- Do not set compaction to `"aggressive"` (invalid)
- Do not use `exec curl` for Brave API (blocked; use web_search)
- Do not skip `chown` after editing config files
- Do not push secrets to git
- Do not set thinkingDefault to anything other than `"off"` for Codex
- Do not remove anti-clarification rules from SOUL.md or SKILL.md
