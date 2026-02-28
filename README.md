# OpenClaw + Sentinel + Job Radar

Production AI system on a Hetzner CPX22 VPS. Gemini-first model stack, targeting **$14-23/month total** (VPS + API).

## Architecture

```
                        +-----------------------------------------------------------+
                        |              Hetzner CPX22 VPS                            |
                        |         Ubuntu 24.04 LTS | 3 vCPU | 4GB RAM              |
                        |                                                           |
  Telegram ----------->|  +-------------------------+  +-----------------------+   |
  (OpenClaw Bot)       |  |    Docker Container      |  |   systemd service     |   |
                        |  |                          |  |                       |   |
                        |  |    OpenClaw Gateway      |  |   Sentinel Bot        |   |
                        |  |    Port 18789 (lo)       |  |   Python + SDK        |   |
                        |  |                          |  |                       |   |
                        |  |  +------+  +----------+  |  |   Flash default       |   |
                        |  |  | main |  |   work   |  |  |   9 tool functions    |   |
  Telegram ----------->|  |  | agent|  |  agent   |  |  |   Strict whitelist    |   |
  (Sentinel Bot)       |  |  |      |  | sandbox  |  |  +-----------------------+   |
                        |  |  +------+  +----------+  |                             |
                        |  +-------------------------+                             |
                        |                                                           |
                        |  +-------------------------+  +-----------------------+   |
                        |  |   job-radar-api          |  |   job-radar-db        |   |
                        |  |   FastAPI / Port 8080    |  |   PostgreSQL 16       |   |
  Telegram <-----------|  |   Brave + HN + RemoteOK  |  |   jobs_normalized     |   |
  (Digest Channel)     |  +-------------------------+  +-----------------------+   |
                        |                                                           |
  SSH Tunnel --------->|  UFW (SSH only) + fail2ban + key-only auth               |
  (Mac Client)        +-----------------------------------------------------------+
```

### Components

| Component | Role | Runtime | Model |
|-----------|------|---------|-------|
| **OpenClaw** | User-facing AI: news briefs, research, job search, scheduling | Docker container | Gemini 2.5 Flash (default) |
| **Sentinel** | Infrastructure sysadmin: Docker, monitoring, security, backups, costs | systemd service | Gemini 2.5 Flash |
| **Job Radar** | Automated job discovery + digests | Docker containers (API + PostgreSQL) | Gemini 2.5 Flash |

### Model Routing

| Tier | Model | Use Case |
|------|-------|----------|
| Default | Gemini 2.5 Flash | Chat, news briefs, heartbeat, job radar, sub-agents |
| Escalation | Gemini 2.5 Pro | Research, complex analysis (manual only) |
| Manual | Claude Sonnet 4.6 | "Think harder" requests |
| Manual | Claude Opus 4.6 | Explicit `/model opus` |

Auto-fallback to Anthropic: DISABLED. Haiku: NEVER used.

---

## News Brief v4

Unified news intelligence system. 1 skill replaces the 9 V3 skills. Topic-flexible, natural language or commands, Telegram-native.

### How to Use

**Natural language** (just say what you want):
```
top ai news                          → AI top 5 this week
top ai news yesterday                → AI stories from yesterday
news about Google last month         → entity-focused (Google) + month scope
latest on fintech                    → any topic works
deep analysis of AI                  → detailed mode (8 stories, 500 words)
what's new in semiconductors         → ad-hoc topic
expert network news                  → ENB industry brief
brief me on crypto last year         → any topic, any timeframe
```

**Commands:**
```
/brief                               → AI top 5 this week (default)
/brief ai top5                       → same, explicit
/brief expert-networks               → ENB industry brief
/brief status                        → system health
/brief help                          → usage guide
/brief ai deep                       → detailed mode
```

**Backward-compatible aliases** (all still work):
```
/ai_daily_brief                      → /brief ai top5
/ai_daily_brief_top5                 → /brief ai top5
/ai_daily_brief_status               → /brief status
/ai_daily_brief_builder              → /brief ai deep
/expert_network_brief                → /brief expert-networks top5
/enb                                 → /brief expert-networks top5
```

### Architecture

```
Files:  2 total (down from 14 in V1)
  skills/news-brief/SKILL.md           ← The one skill (~220 lines)
  workspace/logs/news-brief-state.json ← Runtime state

Search:  Brave LLM Context API via gateway web_search tool
Model:   Gemini 2.5 Flash (all modes, temperature 0)
Output:  top5 ≤200 words, deep ≤500 words
```

### Topics

| Profile | Query Focus |
|---------|-------------|
| `ai` (default) | Model releases, benchmarks, regulation, tooling, open source |
| `expert-networks` | GLG, AlphaSights, Guidepoint, Third Bridge, Capvision + competitors |
| Any ad-hoc | Just say the topic — "fintech", "crypto", "semiconductors", etc. |

### Ranking Rubric

Stories scored 0-100 on 5 weighted factors: Impact (3.0), Credibility (2.5), Novelty (2.0), Freshness (1.5), Confidence (1.0). Penalties for single-source, unverified benchmark claims, and speculation.

### Cron Schedule

| Job | UTC | COT | Model | Timeout |
|-----|-----|-----|-------|---------|
| AI Top 5 | `10 12 * * *` | 07:10 | Flash | 90s |
| ENB Top 5 | `0 12 * * *` | 07:00 | Flash | 90s |

Delivery: Telegram channel `-1003826801947`. Session: isolated.

### Cost

| Metric | V1 (9 skills) | V4 (1 skill) |
|--------|--------------|--------------|
| Files | 14 | 2 |
| Tool calls/run | 6-8 | 2-3 |
| Model | Pro ($0.015-0.03/run) | Flash ($0.003-0.006/run) |
| Monthly | $2.89-3.79 | $0.72-1.20 |

### Error Codes

| Code | Meaning |
|------|---------|
| E01 | Search failed (Brave API error/timeout) |
| E02 | Zero results from Brave |
| E03 | All results outside date window |
| E04 | State file write failed (non-critical) |
| E05 | Telegram delivery failed |
| E06 | Tool call limit reached |

---

## Job Radar

Automated job discovery. Separate Docker containers, sends digests directly via Telegram Bot API.

| Setting | Value |
|---------|-------|
| Connectors | Brave Web Search, HN "Who's Hiring", RemoteOK RSS |
| Digest schedule | AM 08:00 COT, PM 18:00 COT |
| Channel | `-1003826801947` |
| Dedup | Content-based hash |

Commands: `/job_radar`, `/job_search`, `/job_why`, `/job_trends`, `/job_skills`, `/job_hidden`, `/job_save`, `/job_dismiss`, `/job_health`

---

## Sentinel

Infrastructure sysadmin bot. systemd service at `/opt/sentinel/`. 9 tools with whitelist/blocklist security.

| Tool | Description | Safety |
|------|-------------|--------|
| `system_stats` | CPU, RAM, disk, uptime | Read-only |
| `docker_status` | List all containers | Read-only |
| `docker_restart` | Restart a container | Confirmation required |
| `docker_logs` | Tail container logs | Read-only, truncated |
| `run_command` | Shell command | Whitelist-only |
| `check_security` | UFW, fail2ban, ports | Read-only |
| `check_openclaw_health` | Container health | Read-only |
| `backup_openclaw` | Tar.gz config | Safe location only |
| `cost_summary` | API cost tracking | Read-only |

Zero-cost commands: `/status`, `/openclaw`, `/security`, `/backup`, `/cost` — bypass LLM entirely.

---

## Token Optimization

| Optimization | Detail |
|-------------|--------|
| Flash default | All routine work on cheapest model |
| Heartbeat 90m | Bounded to active hours (07:00-23:00 COT) |
| SOUL.md ~800 tokens | Sent with every request, trimmed 63% from original |
| Compaction: safeguard | Only `"default"` and `"safeguard"` are valid |
| Context pruning | cache-ttl 3m, keep 1 last assistant, prune tool output >1K chars |
| contextTokens 32,768 | Hard-caps context window per session |
| Sub-agents on Flash | maxConcurrent=1, timeout 90s, archive after 30m |
| Silent hours | No proactive messages 23:00-07:00 COT |

---

## Project Structure

```
.
├── README.md                              # This file
├── CLAUDE-CODE-HANDOFF.md                 # Handoff for next Claude Code session
├── .gitignore
│
├── sentinel/                              # Sysadmin Bot
│   ├── sentinel.py                        # Agentic loop + tool chaining
│   ├── telegram_handler.py                # Telegram interface + auth
│   ├── config.py                          # Config validation
│   ├── cost_tracker.py                    # API cost accounting
│   ├── tools.py                           # 9 tools + security
│   └── tests/                             # 65+ tests (zero API cost)
│
├── openclaw/                              # OpenClaw Gateway config
│   ├── openclaw-config.json               # Gateway runtime config
│   ├── jobs.json                          # Cron registry (2 jobs)
│   ├── SOUL.md                            # Core personality + routing
│   ├── AGENTS.md                          # Agent registry + model routing
│   ├── CRON.md                            # Cron documentation
│   ├── BOOT.md                            # Startup health checks
│   ├── CHANNELS.md                        # Channel security
│   ├── docker-compose.yml                 # Docker config
│   ├── config/                            # Agent workspace files
│   ├── agents/work/                       # Work agent (sandboxed)
│   ├── skills/
│   │   ├── news-brief/SKILL.md            # News Brief v4 (unified)
│   │   └── job-radar/SKILL.md             # Job Radar commands
│   ├── workspace/logs/
│   │   └── news-brief-state.json          # Brief run state
│   └── memory/
│
├── infrastructure/                        # Deployment scripts
│   ├── deploy.sh, secure.sh               # VPS setup
│   ├── backup.sh, restore.sh              # Backup/restore
│   ├── health-check.sh                    # System health
│   └── ...
│
└── docs/                                  # Documentation
    ├── DEPLOYMENT.md
    ├── TROUBLESHOOTING.md
    └── ...
```

---

## Security

- **Network:** UFW deny-all except SSH, gateway on loopback only, fail2ban, key-only SSH
- **Application:** Sentinel whitelist/blocklist, Telegram user allowlist, Docker isolation (uid=999)
- **Agent isolation:** main/work agents separated, work agent sandboxed
- **Secrets:** `.env` in `.gitignore`, 600 permissions, excluded from backups

---

## Cost

| Component | Monthly |
|-----------|---------|
| Hetzner CPX22 | ~$8 |
| LLM APIs | $4-12 |
| **Total** | **$12-20** |

---

## Quick Start

```bash
# Validate config
python3 -c "import json; json.load(open('openclaw/openclaw-config.json'))"

# Run Sentinel tests
cd sentinel && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pytest tests/ -v

# VPS validation
docker compose ps
systemctl status sentinel --no-pager
cat /root/.openclaw/workspace/logs/news-brief-state.json | python3 -m json.tool
```

### Telegram Smoke Tests
```
/brief status              → system health
/brief help                → usage guide
/brief ai top5             → 5 ranked AI stories
top ai news yesterday      → natural language test
/brief expert-networks     → ENB industry brief
/ai_daily_brief            → backward compat test
```

---

## Known Gotchas

| Issue | Detail |
|-------|--------|
| Config reload | `docker kill --signal=SIGUSR1` logs nothing on success, only errors |
| Compaction modes | Only `"default"` and `"safeguard"` valid. `"aggressive"` silently rejected |
| `heartbeatModel` | NOT valid. Use `agents.defaults.heartbeat.model` |
| SKILL.md `model:` | Prompt hint only, NOT gateway-enforced. Cron `model` IS enforced |
| File ownership | Edit/Write resets to `root:root`. Always `chown sentinel:systemd-journal` after |
| Telegram long-poll | 10s interval is HTTP to Telegram, NOT an LLM call. Zero cost at idle |
| `<think>` tags | Absolute ban — wastes 20K+ tokens and crashes sessions |

---

Private project. Not licensed for redistribution.
