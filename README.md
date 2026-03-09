# OpenClaw + Sentinel + Job Radar

Production AI system on a Hetzner CPX22 VPS. Codex-first model stack, targeting **$9-11/month total** (VPS + API).

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
                        |  |  +------+  +----------+  |  |   Flash (Gemini)      |   |
                        |  |  | main |  |   work   |  |  |   12 tool functions   |   |
  Telegram ----------->|  |  | agent|  |  agent   |  |  |   Strict whitelist    |   |
  (Sentinel Bot)       |  |  |      |  | sandbox  |  |  +-----------------------+   |
                        |  |  +------+  +----------+  |                             |
                        |  +-------------------------+                             |
                        |                                                           |
                        |  +-------------------------+  +-----------------------+   |
                        |  |   job-radar-api          |  |   job-radar-db        |   |
                        |  |   FastAPI / Port 8080    |  |   PostgreSQL 16       |   |
  Telegram <-----------|  |   Brave + HN + RemoteOK  |  |   db: jobradar        |   |
  (Digest Channel)     |  +-------------------------+  +-----------------------+   |
                        |                                                           |
  SSH Tunnel --------->|  UFW (SSH only) + key-only auth                          |
  (Mac Client)        +-----------------------------------------------------------+
```

### Components

| Component | Role | Runtime | Model |
|-----------|------|---------|-------|
| **OpenClaw** | User-facing AI: news briefs, research, job search, scheduling | Docker container | GPT-5.3 Codex (subscription-covered) |
| **Sentinel** | Infrastructure sysadmin: Docker, monitoring, security, backups, costs, cron mgmt | systemd service | Gemini 2.5 Flash |
| **Job Radar** | Automated job discovery + digests | Docker containers (API + PostgreSQL) | None (Brave API only) |

### Model Routing (Codex-first)

| Tier | Model | Use Case |
|------|-------|----------|
| Default | GPT-5.3 Codex | Chat, news briefs, heartbeat, sub-agents, image |
| Fallback | Gemini 2.5 Flash | Only if Codex unavailable |
| Manual | Gemini 2.5 Pro | Research, complex analysis (manual only) |

Auto-fallback to Anthropic: DISABLED. Haiku: NEVER used. API-key models (gpt-4o-mini, gpt-4o): configured but NOT used.

---

## Sentinel

Infrastructure sysadmin bot. systemd service at `/opt/sentinel/`. Google/Gemini 2.5 Flash, max_tokens 1500, 12 tools.

### Tools

| Tool | Description | Safety |
|------|-------------|--------|
| `system_stats` | CPU, RAM, disk, uptime | Read-only |
| `docker_status` | List all containers with CPU/RAM | Read-only |
| `docker_restart` | Restart a container | Allowed containers only |
| `docker_logs` | Tail container logs | Read-only, truncated |
| `run_command` | Shell command | Whitelist-only |
| `check_security` | UFW, ports, failed SSH | Read-only |
| `check_openclaw_health` | Container health + exec-based HTTP probe | Read-only |
| `backup_openclaw` | Tar config + workspace | Safe location only |
| `cost_summary` | VPS-wide cost tracking (Sentinel exact + Docker estimated) | Read-only |
| `check_api_spirals` | Restart count, error rate, Brave volume, loop detection | Read-only |
| `list_scheduled_tasks` | All cron jobs across VPS, OpenClaw, Job Radar, systemd | Read-only |
| `manage_cron` | Enable/disable cron jobs (openclaw, jobradar, system) | Per-job control |

### Zero-Cost Commands

These bypass the LLM entirely — zero token cost:

| Command | Action |
|---------|--------|
| `/status` | System stats + container health |
| `/openclaw` | OpenClaw gateway health |
| `/security` | UFW, ports, failed SSH |
| `/backup` | Create tar backup |
| `/cost [today\|week\|month\|all]` | VPS cost dashboard |
| `/tasks` | All scheduled tasks across VPS |

Plus static responses for: `hi`, `thanks`, `ok`, `help`, `ping`, `what can you do`, `model`, `codex`, `capabilities`.

### Config

| Setting | Value |
|---------|-------|
| Provider | google / gemini-2.5-flash |
| Fallback | anthropic / claude-haiku-4-5 (only on Google failure) |
| max_tokens | 1500 |
| max_tool_iterations | 4 |
| conversation_ttl | 900s |
| rate_limit | 15 requests / 300s |
| usd_to_cop_rate | 4000 |
| cost_tracking | Exact via JSONL + atomic JSON summary |

---

## News Brief v4

Unified news intelligence system. 1 skill replaces the 9 V3 skills. Topic-flexible, natural language or commands, Telegram-native.

### How to Use

**Natural language** (just say what you want):
```
top ai news                          -> AI top 5 this week
top ai news yesterday                -> AI stories from yesterday
news about Google last month         -> entity-focused (Google) + month scope
latest on fintech                    -> any topic works
deep analysis of AI                  -> detailed mode (8 stories, 500 words)
what's new in semiconductors         -> ad-hoc topic
expert network news                  -> ENB industry brief
brief me on crypto last year         -> any topic, any timeframe
```

**Commands:**
```
/brief                               -> AI top 5 this week (default)
/brief ai top5                       -> same, explicit
/brief expert-networks               -> ENB industry brief
/brief status                        -> system health
/brief help                          -> usage guide
/brief ai deep                       -> detailed mode
```

### Cron Schedule

| Job | UTC | COT | Model | Timeout | Status |
|-----|-----|-----|-------|---------|--------|
| AI Top 5 | `10 12 * * *` | 07:10 | Codex | 120s | **DISABLED** |
| ENB Top 5 | `0 12 * * *` | 07:00 | Codex | 120s | **DISABLED** |

Delivery: Telegram channel `-1003826801947`. Session: isolated.

> **Note:** Cron jobs are currently disabled pending Discord migration. Can be re-enabled by setting `enabled: true` in `jobs.json` and reloading config.

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

## Job Radar v3

Automated job discovery. Separate Docker containers, sends digests directly via Telegram Bot API. No LLM cost.

| Setting | Value |
|---------|-------|
| Connectors | Brave, HN "Who's Hiring", RemoteOK, WWR, Jobicy, Watchlist |
| Digest delivery | On-demand via `/job_radar`; scheduled digests handled outside Job Radar APScheduler |
| Channel | `-1003826801947` |
| Dedup | Content-based hash |
| Enrichment | Brave API (no LLM) |
| Status | **3 scheduler jobs ACTIVE** (`discovery_sync`, `watchlist_sync`, `cleanup`) |

> **Note:** Job Radar APScheduler currently runs discovery, watchlist sync, and cleanup. Digests are not scheduled here; they are handled by OpenClaw flows and on-demand skill usage.

Commands: `/job_radar`, `/job_search`, `/job_why`, `/job_trends`, `/job_skills`, `/job_hidden`, `/job_save`, `/job_dismiss`, `/job_health`

---

## Configuration

| Setting | Value |
|---------|-------|
| contextTokens | 65,536 |
| contextPruning | cache-ttl, 3m TTL, keep 2 last assistants, prune tool output >500 chars |
| compaction | safeguard |
| thinkingDefault | off (Codex reasons internally regardless) |
| Session timeout | 300s |
| Sub-agent model | GPT-5.3 Codex |
| Sub-agent timeout | 120s |
| maxConcurrent | 2 sessions |
| Heartbeat | every 180m, active hours 07:00-23:00 COT, model: Codex |
| Codex tuning | bias to action, no clarification questions, no preamble |

---

## Project Structure

```
.
├── README.md
├── ARCHITECTURE.md
├── CLAUDE-CODE-HANDOFF.md
├── .gitignore
│
├── sentinel/                              # Sysadmin Bot source
│   ├── sentinel.py                        # Agentic loop + tool chaining
│   ├── telegram_handler.py                # Telegram interface + auth
│   ├── config.py                          # Config validation
│   ├── cost_tracker.py                    # API cost accounting
│   ├── tools.py                           # 12 tools + security
│   ├── sentinel.service
│   ├── requirements.txt
│   └── tests/                             # 104 tests (mocked, zero API cost)
│
├── openclaw/                              # OpenClaw Gateway config
│   ├── openclaw-config.json               # Config template (secrets placeholder)
│   ├── jobs.json                          # Cron registry (2 jobs: AI + ENB briefs)
│   ├── docker-compose.yml                 # Docker config
│   ├── SOUL.md, AGENTS.md, CRON.md
│   ├── config/                            # Workspace file templates
│   ├── skills/
│   │   ├── news-brief/SKILL.md            # News Brief v4 (~410 lines)
│   │   └── job-radar/SKILL.md             # Job Radar commands
│   └── workspace/                         # Runtime workspace structure
│
├── job-radar/                             # Job Radar v3
│   ├── docker-compose.v3.yml
│   └── v3/                                # FastAPI app source
│
├── infrastructure/                        # Deployment scripts
│   ├── deploy.sh, secure.sh, backup.sh, restore.sh
│   ├── health-check.sh, reload-config.sh
│   ├── docker-compose.yml, Dockerfile
│   └── ...
│
└── docs/                                  # Documentation
    ├── DEPLOYMENT.md, TROUBLESHOOTING.md, COST-MANAGEMENT.md
    ├── setup/, security/, playbooks/, templates/, research/
    └── ...
```

---

## Security

- **Network:** UFW deny-all except SSH, gateway on loopback only, key-only SSH
- **Application:** Sentinel whitelist/blocklist, Telegram user allowlist, Docker isolation (uid=999)
- **Agent isolation:** main/work agents separated, work agent sandboxed
- **Secrets:** `.env` files in `.gitignore`, never committed. No real keys in repo.
- **Telegram:** 2 bots (OpenClaw Bot + Sentinel Bot), delivery channel `-1003826801947`

---

## Cost

| Component | Monthly |
|-----------|---------|
| Hetzner CPX22 | ~$8 |
| Codex (subscription-covered) | $0 |
| Sentinel LLM (Flash) | ~$1-3 |
| Brave API | Free tier |
| **Total** | **$9-11** |

Down from $14-23/month with the Flash-only stack.

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

### Telegram Smoke Tests — Sentinel
```
/status                    -> System stats + all 3 containers
/openclaw                  -> Gateway health, HTTP: 200
/security                  -> UFW, ports, failed SSH
/cost today                -> VPS cost dashboard with model breakdown
/tasks                     -> All cron jobs across VPS
/backup                    -> Create config backup
hi                         -> Static response (zero cost)
check for api spirals      -> Gateway log analysis
restart the openclaw gateway -> Container restart
pause all cron jobs on job radar -> Scheduler pause
```

### Telegram Smoke Tests — OpenClaw
```
/brief status              -> system health
/brief help                -> usage guide
/brief ai top5             -> 5 ranked AI stories
top ai news yesterday      -> natural language test
/brief expert-networks     -> ENB industry brief
```

---

## Known Gotchas

| Issue | Detail |
|-------|--------|
| SIGUSR1 reload | Can trigger exit-0. `on-failure:5` won't auto-restart. Use `docker compose down && up -d` instead |
| File ownership | Edit/Write resets to `root:root`. Always `chown sentinel:systemd-journal` for `/root/.openclaw/*`, `sentinel:sentinel` for `/opt/sentinel/*.py` AND `__pycache__/*.pyc` |
| Compaction modes | Only `"default"` and `"safeguard"` valid. `"aggressive"` silently rejected |
| `heartbeatModel` | NOT valid. Use `agents.defaults.heartbeat.model` |
| SKILL.md `model:` | Prompt hint only, NOT gateway-enforced. Cron `model` IS enforced |
| `<think>` tags | Absolute ban -- crashes sessions, wastes 20K+ tokens |
| thinkingDefault | Must be `"off"` for Codex (model reasons internally regardless) |
| Codex behavior | Tuned for "bias to action" -- no clarification questions, no preamble messages |
| Telegram long-poll | 10s interval is HTTP to Telegram, NOT an LLM call. Zero cost at idle |
| HTTP health probe | Runs `curl` inside container via `exec_run()`. Host HTTP never reaches gateway (connection reset). |
| `.pyc` ownership | Python bytecache in `__pycache__/` must be `sentinel:sentinel`. Root-owned `.pyc` causes silent import failures. |

---

Private project. Not licensed for redistribution.
