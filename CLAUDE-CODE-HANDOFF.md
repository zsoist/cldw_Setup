# Claude Code Handoff

> Last updated: 2026-02-28 | News Brief v4 deployed
>
> **Start here:** Read `README.md` for architecture, this file for deployment state.

---

## Current State

All services healthy. News Brief v4 deployed and tested (both cron jobs returned `ok`).

### Recent Changes (2026-02-28)

**News Brief v4 migration** — consolidated 9 skills + 5 state/config files into 1 skill + 1 state file:
- Created `skills/news-brief/SKILL.md` with XML-tagged Flash prompting, 12 few-shot NL examples, scoring rubric
- Removed 9 old skill directories (ai-daily-brief-*, expert-network-brief-*)
- Removed old state files (ai-brief-state.json, enb-state.json)
- Updated jobs.json: 3 jobs → 2 jobs, Pro → Flash, 180s → 90s timeout, added temperature=0
- Updated AGENTS.md, SOUL.md, CRON.md for V4 routing
- Fixed exec curl → web_search (gateway blocks exec elevated in cron sessions)

---

## Critical File Paths

### Live (on VPS)

| File | Purpose |
|------|---------|
| `/root/.openclaw/openclaw.json` | Gateway runtime config |
| `/root/.openclaw/skills/news-brief/SKILL.md` | News Brief v4 skill |
| `/root/.openclaw/workspace/logs/news-brief-state.json` | Brief run state |
| `/root/.openclaw/cron/jobs.json` | Cron registry (2 jobs) |
| `/root/.openclaw/workspace/SOUL.md` | Core personality + routing |
| `/root/.openclaw/workspace/AGENTS.md` | Agent registry |
| `/root/.openclaw/workspace/CRON.md` | Cron docs |
| `/opt/sentinel/*.py` | Sentinel source |
| `/etc/sentinel/sentinel.env` | Sentinel env vars |
| `/root/openclaw/docker-compose.yml` | Docker config (AIDB_BRAVE_* vars) |

### Repo (this repo)

| File | Mirrors |
|------|---------|
| `openclaw/skills/news-brief/SKILL.md` | `/root/.openclaw/skills/news-brief/SKILL.md` |
| `openclaw/jobs.json` | `/root/.openclaw/cron/jobs.json` |
| `openclaw/SOUL.md` | `/root/.openclaw/workspace/SOUL.md` |
| `openclaw/AGENTS.md` | `/root/.openclaw/workspace/AGENTS.md` |
| `openclaw/CRON.md` | `/root/.openclaw/workspace/CRON.md` |
| `openclaw/openclaw-config.json` | `/root/.openclaw/openclaw.json` |

---

## File Ownership Rules

**CRITICAL:** Editing files resets ownership to `root:root`. Always fix after:

```bash
# After editing any OpenClaw config:
chown sentinel:systemd-journal /root/.openclaw/skills/news-brief/SKILL.md
chown sentinel:systemd-journal /root/.openclaw/workspace/SOUL.md
chown sentinel:systemd-journal /root/.openclaw/cron/jobs.json
# etc — all files in /root/.openclaw/ must be sentinel:systemd-journal, 640

# After editing Sentinel source:
chown sentinel:sentinel /opt/sentinel/*.py
```

---

## Cron Jobs (2 total)

| Job ID | Name | Schedule (UTC) | COT | Model |
|--------|------|---------------|-----|-------|
| `news-brief-ai` | AI Top 5 | `10 12 * * *` | 07:10 | Flash |
| `news-brief-enb` | ENB Top 5 | `0 12 * * *` | 07:00 | Flash |

Test a cron job: `docker exec openclaw-openclaw-gateway-1 npx openclaw cron run news-brief-ai --expect-final --timeout 120000`

---

## Deployment

```bash
# 1. Sync config to VPS
cp openclaw/skills/news-brief/SKILL.md /root/.openclaw/skills/news-brief/SKILL.md
cp openclaw/SOUL.md /root/.openclaw/workspace/SOUL.md
cp openclaw/AGENTS.md /root/.openclaw/workspace/AGENTS.md
cp openclaw/jobs.json /root/.openclaw/cron/jobs.json

# 2. Fix ownership
chown -R sentinel:systemd-journal /root/.openclaw/skills/news-brief/
chown sentinel:systemd-journal /root/.openclaw/workspace/SOUL.md /root/.openclaw/workspace/AGENTS.md /root/.openclaw/cron/jobs.json
chmod 640 /root/.openclaw/skills/news-brief/SKILL.md /root/.openclaw/workspace/SOUL.md /root/.openclaw/workspace/AGENTS.md /root/.openclaw/cron/jobs.json

# 3. Reload gateway
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1

# 4. Verify
docker exec openclaw-openclaw-gateway-1 npx openclaw skills list
docker exec openclaw-openclaw-gateway-1 npx openclaw cron list
```

---

## Known Gotchas

| Issue | Detail |
|-------|--------|
| `exec elevated` blocked | Gateway blocks `exec` tool in cron sessions. Use `web_search` for Brave queries. |
| Config reload silent | SIGUSR1 logs nothing on success, only errors. |
| Compaction modes | Only `"default"` and `"safeguard"` valid. |
| `<think>` tags | Absolute ban in SKILL.md + SOUL.md — wastes 20K tokens, crashes sessions. |
| AIDB_BRAVE_* vars | Hard caps for web_search. Currently: count=5, max_tokens=1024, threshold=strict (set in container env). |
| State file overwrite | Both cron jobs write to same state file. Last writer wins. Non-critical. |
| temperature in frontmatter | SKILL.md `temperature: 0` is a prompt hint, NOT gateway-enforced. Added to cron payloads too. |

---

## What NOT to Change

- Do not enable auto-fallback to Anthropic (cost explosion)
- Do not use Haiku (banned)
- Do not set compaction to `"aggressive"` (invalid)
- Do not use `exec curl` for Brave API (blocked; use web_search)
- Do not skip `chown` after editing config files
- Do not push secrets to git
