# OpenClaw + Sentinel + Job Radar: Cost-Optimized AI System

A production dual-bot AI system on a Hetzner CPX22 VPS, targeting **$14-23/month total** (VPS + API). OpenClaw is the personal AI gateway, Sentinel is the autonomous sysadmin bot, and Job Radar handles automated job discovery and digests -- all on a Gemini-first model stack (Anthropic Sonnet/Opus available for manual override only).

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

## Design Philosophy

**Gateway Runtime Model.** OpenClaw is a persistent gateway process -- not just a chatbot. It maintains long-running Telegram channel connections, dispatches messages to agent runtimes, and manages tool execution.

**Multi-Agent Architecture.** Two agent profiles run within the gateway -- `main` (personal) and `work` (professional). Each has separate workspace files, memory, tool policies, and risk profiles. The work agent runs in an agent-scope sandbox for data isolation.

**Tenant-Landlord Model.** OpenClaw is the "tenant" -- it handles user-facing tasks inside a resource-constrained Docker container. Sentinel is the "landlord" -- it monitors the system, manages Docker, runs security audits, and creates backups. Neither can interfere with the other.

**Zero-Trust API Cost Control.** Every design decision prioritizes minimizing LLM API spend without sacrificing utility. The system targets **$14-23/month total** (VPS + API combined).

## Token Optimization Strategy

### 1. Four-Tier Model Routing (Gemini-first)

| Tier | Model | Use Case | Cost Factor |
|------|-------|----------|-------------|
| **Default** | Gemini 2.5 Flash | Chat, Q&A, heartbeat, task tracking, sub-agents | ~0.3x |
| **Standard** | Gemini 2.5 Pro | AI Daily Brief cron synthesis, research | ~2x |
| **Premium** | Claude Sonnet 4.6 | "Think harder" / production-grade (manual) | ~5x |
| **Manual Only** | Claude Opus 4.6 | Complex architecture decisions | ~60x |

Default traffic stays on Flash. Escalation to Pro happens for synthesis-heavy cron jobs. Sonnet and Opus are manual-only.

### 2. Heartbeat Alignment

The heartbeat interval is set to **90 minutes** to minimize recurring prompt overhead while maintaining session awareness.

```
Heartbeat:  |-------- 90 min --------|-------- 90 min --------|
                   ^ low-cost pulse          ^ low-cost pulse
```

Active hours are bounded -- no heartbeat during silent hours (23:00-07:00 COT).

### 3. System Prompt Engineering

`SOUL.md` is engineered to **~800 tokens (~3.2KB)** -- trimmed 63% from the original 8.8KB. Every token in this file is sent with every API request, so the cost compounds across thousands of interactions.

- Structured for LLM parsing -- headers, bullet points, no prose
- Specificity-balanced -- enough context to be useful, not so much it wastes tokens
- Priority-ordered -- most important rules first (early attention gets weighted more)

### 4. Conversation Compaction

Compaction mode: `safeguard`. Automatically compresses long conversation histories. Without compaction, a 50-message conversation could consume 10,000+ input tokens per new request.

> **Note:** The only valid compaction mode values are `"default"` and `"safeguard"`. The value `"aggressive"` is **not valid** and causes `Invalid config` on reload -- the gateway silently keeps the last good config.

### 5. Context Pruning

```json
{
  "contextPruning": {
    "mode": "cache-ttl",
    "ttl": "30m",
    "keepLastAssistants": 3,
    "minPrunableToolChars": 50000
  }
}
```

Prunes stale tool results and old assistant turns from context after 30 minutes, keeping the 3 most recent assistant messages. Only prunes tool output blocks larger than 50K characters.

### 6. Context Token Limit

`contextTokens` is set to **65,536** per session (reduced from the 131K default and 1M overrides). This hard-caps the context window to prevent runaway input token costs.

### 7. Silent Hours Optimization

No proactive messages between 23:00-07:00 COT. This eliminates unnecessary API calls while preserving the single scheduled AI brief run at 07:10 COT.

### 8. Response Token Caps

| Component | Max Tokens |
|-----------|-----------|
| OpenClaw responses | 2,048 |
| Sentinel responses | 768 (`SENTINEL_MAX_TOKENS`) |
| Bot instruction | "Keep under 300 words" |

### 9. Resource-Constrained Container Limits

```yaml
deploy:
  resources:
    limits:
      cpus: "2.0"      # 2 of 3 vCPUs for OpenClaw
      memory: 2560M     # 2.5GB of 4GB for OpenClaw
    reservations:
      cpus: "1.0"
      memory: 1024M
```

Leaves 1 vCPU and ~1.5GB RAM for Sentinel + Job Radar + OS overhead.

### 10. Sub-agent Constraints

- Model: Gemini 2.5 Flash (same as default -- no accidental Pro escalation)
- `maxConcurrent`: 1
- `runTimeoutSeconds`: 90
- `archiveAfterMinutes`: 30

### 11. Zero-Cost Operations

Several interaction paths bypass the LLM entirely:

| Path | Mechanism |
|------|-----------|
| Sentinel `/status`, `/openclaw`, `/security`, `/backup`, `/cost` | Direct tool execution + Python formatting |
| Sentinel "hi", "hello", "thanks", "ok", "help", "ping" | Static response handler |
| Telegram idle polling (10s long-poll) | HTTP to Telegram only -- zero token cost |

### 12. Cron Architecture

3 scheduled jobs. Everything else runs on-demand.

| # | Job | Schedule (UTC) | Schedule (COT) | Model | Timeout |
|---|-----|----------------|----------------|-------|---------|
| 1 | AI Daily Brief Top5 (Previous Day) | `10 12 * * *` | 07:10 daily | Gemini 2.5 Pro | 180s |
| 2 | Expert Network Brief (Morning) | `0 12 * * *` | 07:00 daily | Gemini 2.5 Flash | 120s |
| 3 | Expert Network Brief (Evening) | `0 23 * * *` | 18:00 daily | Gemini 2.5 Flash | 90s |

Session: isolated. Delivery: Telegram channel `-1003826801947`. Max concurrent runs: 1.

### 13. Additional Tuning

- `thinkingDefault`: off (prevents thinking blocks in Telegram responses)
- `verboseDefault`: off
- `maxConcurrentTasks`: 4
- `imageModel`: Gemini 2.5 Flash (not Pro)
- Session timeout: 300s

## AI Daily Brief

Source-grounded AI briefing with Brave LLM Context API grounding. One automated daily run plus on-demand modes.

### Commands

```
/ai_daily_brief top5              # Previous day top 5 (default cron mode)
/ai_daily_brief top5 12h|week     # Adjustable time window
/ai_daily_brief morning           # Morning planning brief (Pro)
/ai_daily_brief evening           # Evening recap (Pro)
/ai_daily_brief builder           # Builder/developer focus (Pro)
/ai_daily_brief watchlist         # Custom topic watchlist (Flash)
/ai_daily_brief status            # Diagnostic: last run, state health (Flash)
/ai_daily_brief help              # Full command reference
/ai_daily_brief history [n]       # Last N runs with status + cost
/ai_daily_brief diff              # Compare last two runs
/ai_daily_brief feedback <id> <1-5> [comment]
/ai_daily_brief watchlist add|remove <topic>
```

Compatibility aliases: `/ai_daily_brief_top5`, `/ai_daily_brief_morning`, etc.

### Quality Gates

- Weighted anti-hype ranking (impact 0.28, credibility 0.22, novelty 0.18, relevance 0.14, freshness 0.10, confidence 0.08)
- Mandatory `YYYY-MM-DD` event dates per story -- vague or undated stories are rejected
- Technical details per top story: architecture, parameter count, context window, benchmarks
- Mandatory citations as clickable markdown hyperlinks
- Builder corner, strategic take, and explicit confidence/gaps section

### State Management

- State file: `workspace/logs/ai-brief-state.json` (schema v5)
- Deduplication and update suppression prevent duplicate runs
- Stale `last_run.status="running"` locks cleared by `infrastructure/reconcile-ai-brief-state.sh`
- Monthly archive: `workspace/outputs/summaries/ai-brief-stories-YYYY-MM.json`
- Output channel: `-1003826801947` (Telegram channel, bot is admin)

## Expert Network Intelligence Brief

Automated competitive intelligence on the expert network industry, tailored for Dialectica. Monitors 8 competitors for AI capabilities, product launches, and strategic moves.

### Competitors Monitored
GLG, AlphaSights, Guidepoint, Third Bridge, Capvision, Prospex (by Capvision), Coleman Research, Atheneum Partners. Also tracks Dialectica for market positioning context.

### Commands
```
/expert_network_brief                  # Full morning scan (default)
/expert_network_brief morning          # Full scan
/expert_network_brief evening          # Delta since morning
/expert_network_brief status           # Last run + health
/expert_network_brief help             # Command reference
/enb                                   # Shorthand for morning scan
/expert_network_brief_status           # Status alias
```

### Intelligence Priorities (ranked)
1. **AI capabilities, features, products** (HIGHEST — Dialectica's strategic focus)
2. Strategic moves — acquisitions, mergers, partnerships, funding
3. Market expansion — new geographies, verticals, client segments
4. Leadership changes, industry trends

### Cost Profile
- Model: **Gemini 2.5 Flash** (structured search + summary — no deep synthesis needed)
- Brave queries: 2-3 per morning scan, 1-2 per evening delta
- Est. cost per run: ~$0.005 | Daily (2 runs): ~$0.01 | Monthly: ~**$0.30**
- State file: `workspace/logs/enb-state.json`

### Schedule
| Scan | UTC | COT | Mode |
|------|-----|-----|------|
| Morning | 12:00 | 07:00 | Full scan (2-3 Brave queries) |
| Evening | 23:00 | 18:00 | Delta update (new findings only) |

## Job Radar

Automated job discovery and digest system running as separate Docker containers.

### Production Config

| Setting | Value |
|---------|-------|
| `JOB_SEARCH_BRAVE_ONLY` | `false` (HN + RemoteOK connectors enabled alongside Brave) |
| `BRAVE_RESULTS_PER_QUERY` | 8 |
| `BRAVE_CONTEXT_MAX_TOKENS` | 3,072 |
| `BRAVE_CONTEXT_MAX_SNIPPETS` | 20 |
| `BRAVE_DISCOVERY_TARGET_JOBS` | 24 |
| `JOB_MAX_AGE_DAYS` | 45 |
| `HEALTH_EXTERNAL_CHECK_TTL_SECONDS` | 10,800 (3 hours) |
| `llm_standard_model` | Gemini 2.5 Flash |

### Connectors

- **Brave Web Search** -- ATS-filtered (greenhouse.io, lever.co, workable.com)
- **Hacker News** -- "Who's Hiring" threads
- **RemoteOK RSS** -- remote job feed (company field fix applied)

### Health Optimization

Health checks are zero-cost:
- Brave: uses cheap web search endpoint
- Anthropic: empty-messages validation (400 = key valid)
- External check TTL: 3 hours (prevents excessive API calls from dashboards)

### Digest Schedule

| Digest | UTC | COT |
|--------|-----|-----|
| AM | 13:00 | 08:00 |
| PM | 23:00 | 18:00 |

Digests are sent directly via Telegram Bot API to channel `-1003826801947` (not via OpenClaw).

Content-based dedup hash ensures identical job sets don't produce duplicate digests.

## Sentinel: Agentic Sysadmin Bot

Runs as a systemd service at `/opt/sentinel/`. Primary: Google Gemini Flash. Anthropic (Sonnet/Opus) available for manual override only -- auto-fallback is disabled.

### Tool Architecture

9 tools with strict safety controls:

| Tool | Description | Safety |
|------|-------------|--------|
| `system_stats` | CPU, RAM, disk, uptime | Read-only |
| `docker_status` | List all containers | Read-only |
| `docker_restart` | Restart a container | Requires confirmation |
| `docker_logs` | Tail container logs (max 200 lines) | Read-only, truncated |
| `run_command` | Execute shell command | **Whitelist-only**, blocklist enforced |
| `check_security` | UFW, fail2ban, open ports audit | Read-only |
| `check_openclaw_health` | Container state + health + recent errors | Read-only |
| `backup_openclaw` | Tar.gz config + workspace | Write (safe location only) |
| `cost_summary` | API cost tracking summary | Read-only |

### Zero-Cost Slash Commands

These commands execute tools directly and format results in Python -- no LLM call:

- `/status` -- system stats
- `/openclaw` -- OpenClaw health
- `/security` -- security audit
- `/backup` -- run backup
- `/cost` -- cost summary

### Command Whitelist Security

The `run_command` tool implements a **dual-layer filter**:

1. **Blocklist** (runs first): rejects destructive patterns (`rm`, `sudo su`, `apt`, `wget`, `reboot`, `chmod 777`)
2. **Whitelist** (argument-aware): only allows explicitly validated command shapes (`df -h`, `systemctl status <unit>`, `docker ps`, local-only `curl`)

Unknown commands are rejected by default (deny-by-default posture).

### Cost Tracking

- Append-only event log: `/var/log/sentinel/api-usage.jsonl`
- Aggregated summary: `/var/log/sentinel/api-cost-summary.json`
- Every Telegram reply appends: `Tokens used: in/out - USD $... / COP $...`
- COP rate: `SENTINEL_USD_TO_COP_RATE=4000`
- Token tracking uses `getattr()` on Gemini proto objects (fixed -- was returning 0 due to proto attribute access bug)

### Agentic Loop

```python
for _ in range(max_tool_iterations):    # Capped at 4
    response = client.generate(
        model="gemini-2.5-flash",
        tools=TOOLS,
        messages=history,
    )
    if has_tool_calls(response):
        result = execute_tool(call.name, call.args)
        history.append(tool_result)
        continue
    else:
        return text_response              # Final answer
```

### Configuration

| Setting | Value |
|---------|-------|
| `SENTINEL_PROVIDER` | `google` |
| `SENTINEL_MAX_TOKENS` | 768 |
| `SENTINEL_MAX_TOOL_ITERATIONS` | 4 |
| `SENTINEL_CONVERSATION_TTL_SECONDS` | 900 |
| `SENTINEL_USD_TO_COP_RATE` | 4000 |

## Project Structure

```
.
├── README.md                              # This file
├── CLAUDE-CODE-HANDOFF.md                 # Project state + handoff for next session
├── .gitignore                             # Excludes .env, keys, caches
│
├── sentinel/                              # Sysadmin Bot (Gemini/Anthropic dual-provider)
│   ├── sentinel.py                        # Agentic loop with tool chaining
│   ├── telegram_handler.py                # Telegram interface + auth
│   ├── config.py                          # Dataclass config with validation
│   ├── cost_tracker.py                    # Crash-safe API cost accounting
│   ├── tools.py                           # 9 tools + whitelist/blocklist security
│   ├── requirements.txt                   # Python dependencies
│   ├── sentinel.service                   # systemd unit file
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                    # Shared fixtures (mocked provider clients)
│       ├── test_tools.py                  # Whitelist, tool dispatch, Docker mocks
│       ├── test_telegram.py               # Auth, commands, message handling
│       ├── test_config.py                 # Config parsing edge cases
│       ├── test_cost_tracker.py           # Cost tracking + aggregation
│       └── test_provider_fallback.py      # Gemini<->Anthropic fallback logic
│
├── openclaw/                              # OpenClaw Gateway configuration
│   ├── openclaw-config.json               # Gateway runtime config (schema-valid)
│   ├── jobs.json                          # Cron job registry (3 jobs: AI brief + ENB AM/PM)
│   ├── docker-compose.yml                 # Docker config with resource limits
│   ├── SOUL.md                            # Root SOUL (runtime bootstrap)
│   ├── BOOT.md                            # Startup health checks
│   ├── AGENTS.md                          # Root agent config
│   ├── CHANNELS.md                        # Channel security policy
│   ├── CRON.md                            # Cron registry
│   ├── config/                            # Main agent workspace files (12 files)
│   │   ├── SOUL.md                        # Orchestrator identity (~800 tokens)
│   │   ├── USER.md                        # User profile + preferences
│   │   ├── AGENTS.md                      # Sub-agent registry + model routing
│   │   ├── TOOLS.md                       # Tool policy + permissions
│   │   ├── HEARTBEAT.md                   # 90-min interval + active hours
│   │   ├── MEMORY.md                      # Persistent memory + daily log system
│   │   ├── IDENTITY.md                    # Persona tone + style
│   │   ├── BOOTSTRAP.md                   # First-run behavior
│   │   ├── BOOT.md                        # Startup health checks
│   │   ├── CRON.md                        # Cron registry
│   │   ├── CHANNELS.md                    # Channel security + allowlists
│   │   └── SANDBOX.md                     # Sandbox + agent isolation rules
│   ├── agents/
│   │   └── work/                          # Work agent -- sandboxed
│   │       ├── SOUL.md                    # Professional-only scope
│   │       ├── TOOLS.md                   # Restricted tool policy
│   │       ├── USER.md                    # Work-context profile
│   │       ├── MEMORY.md                  # Work-specific memory (isolated)
│   │       └── HEARTBEAT.md               # Work-hours schedule
│   ├── skills/
│   │   ├── ai-daily-brief/SKILL.md        # Canonical AI brief command
│   │   ├── ai-daily-brief-top5/SKILL.md   # Top5 alias (Flash)
│   │   ├── ai-daily-brief-morning/SKILL.md
│   │   ├── ai-daily-brief-evening/SKILL.md
│   │   ├── ai-daily-brief-builder/SKILL.md
│   │   ├── ai-daily-brief-status/SKILL.md
│   │   ├── ai-daily-brief-watchlist/SKILL.md
│   │   ├── expert-network-brief/SKILL.md  # Competitor intel (Flash, 2x daily)
│   │   ├── expert-network-brief-status/SKILL.md # ENB status alias
│   │   ├── daily-briefing/SKILL.md        # Morning planning briefing
│   │   ├── job-radar/SKILL.md             # Job Radar command router
│   │   ├── research-assistant/SKILL.md    # Deep research (Pro, on-demand)
│   │   └── task-tracker/SKILL.md          # Task management (Flash)
│   ├── workspace/
│   │   ├── personal/                      # Personal context (main agent)
│   │   │   ├── goals.md
│   │   │   ├── routines.md
│   │   │   └── projects/
│   │   ├── business/                      # Professional context (work agent)
│   │   │   ├── goals-okrs.md
│   │   │   ├── operating-rules.md
│   │   │   └── projects/ (active/ + archived/)
│   │   ├── outputs/
│   │   │   ├── summaries/                 # Daily briefs, monthly archives
│   │   │   ├── reports/
│   │   │   ├── drafts/
│   │   │   └── exports/
│   │   └── logs/
│   │       ├── change-log.md              # Config change record
│   │       ├── cron-job-results.md        # Cron execution log
│   │       └── ai-brief-state.json        # Stateful dedupe + slot tracking
│   └── memory/
│       └── weekly/                        # Weekly review summaries
│
├── infrastructure/                        # Deployment & operations
│   ├── Dockerfile                         # OpenClaw container build
│   ├── docker-compose.yml                 # Resource limits tuned for CPX22
│   ├── env.template                       # Secret placeholders (never committed)
│   ├── ssh-config-snippet                 # Mac SSH config with tunnel
│   ├── deploy.sh                          # One-shot VPS deployment
│   ├── secure.sh                          # UFW + fail2ban + SSH hardening
│   ├── backup.sh                          # Automated backup (7-day rotation)
│   ├── restore.sh                         # Interactive restore from backup
│   ├── health-check.sh                    # Multi-check system health
│   ├── sync-sentinel-env.sh               # Sync .env -> /etc/sentinel/sentinel.env
│   ├── sync-openclaw-config.sh            # Render openclaw.json from .env
│   ├── validate-placeholders.sh           # Validate secrets are non-placeholder
│   ├── aibrief-smoke-test.sh              # AI brief health + token smoke test
│   ├── vps-rollout-aibrief.sh             # Config-only AI brief rollout
│   ├── merge-ai-brief-state.sh            # Template->runtime state merge
│   ├── reconcile-ai-brief-state.sh        # Auto-close stale running locks
│   ├── set-aibrief-output-channel.sh      # Configure AI brief output channel
│   ├── reset-openclaw-telegram-sessions.sh # Reset stale Telegram sessions
│   ├── reset-telegram-offset.sh           # Reset Telegram update offsets
│   ├── update-api-cost-rollup.sh          # Merge AI Brief + Sentinel costs
│   └── vps-activate-channel-commands.sh   # Activate channel command routing
│
└── docs/
    ├── DEPLOYMENT.md                      # Step-by-step deployment guide
    ├── COST-MANAGEMENT.md                 # Budget tracking + optimization
    ├── TROUBLESHOOTING.md                 # Common issues + recovery
    ├── PHASE3-CHECKLIST.md                # Go-live verification checklist
    ├── setup/
    │   ├── model-routing-policy.md        # Model routing reference
    │   └── performance-tuning.md          # API cost + responsiveness tuning
    ├── security/
    │   ├── access-boundaries.md           # Agent/channel access matrix
    │   ├── openclaw-hardening.md          # Gateway security hardening
    │   └── secrets-rotation.md            # Secret rotation procedure
    ├── playbooks/
    │   ├── ai-daily-brief.md              # AI brief pipeline + quality gates
    │   ├── daily-planning.md              # Daily brief playbook
    │   ├── personal-weekly-review.md      # Weekly review playbook
    │   ├── meeting-prep.md                # Meeting preparation playbook
    │   └── decision-log-template.md       # Decision record format
    ├── templates/
    │   ├── ai-daily-brief-template.md     # AI brief output format
    │   ├── brief-template.md              # Executive brief format
    │   ├── research-summary-template.md   # Research output format
    │   └── sop-template.md                # Standard operating procedure
    └── research/
        └── job-search-automation.md       # Job search implementation plan
```

## Cost Projections

### Monthly Operating Cost

| Component | Cost |
|-----------|------|
| Hetzner CPX22 (3 vCPU, 4GB, 80GB NVMe) | ~$8 |
| LLM APIs (Gemini-first, Anthropic manual-only) | $6-15 |
| **Total** | **$14-23** |

### Per-Interaction Cost Breakdown

| Interaction Type | Model | Estimated Cost |
|-----------------|-------|----------------|
| Simple Q&A / chat | Gemini 2.5 Flash | ~$0.0005-0.001 |
| Heartbeat cycle (every 90 min) | Gemini 2.5 Flash | ~$0.0003-0.0008 |
| Daily planning briefing | Gemini 2.5 Flash | ~$0.001-0.002 |
| AI Daily Brief (cron) | Gemini 2.5 Pro | ~$0.01-0.03 |
| Research deep dive | Gemini 2.5 Pro | ~$0.01-0.03 |
| Sentinel `/status`, `/openclaw`, `/cost` | None (zero-cost) | $0.00 |
| Sentinel "hi", "hello", "ping" | None (static) | $0.00 |
| Sentinel agentic query | Gemini 2.5 Flash | ~$0.001-0.003 |
| Complex analysis (manual) | Opus 4.6 | $0.10-0.30 |

With ~50-100 daily interactions (mostly Flash + zero-cost commands), monthly API cost stays within the $6-15 target.

## Security Model

### Network
- **UFW**: deny-all inbound except SSH (port 22)
- **OpenClaw gateway**: bound to loopback (port 18789) -- accessible only via SSH tunnel
- **fail2ban**: 3 failed attempts = 1 hour ban
- **SSH**: key-only authentication, password auth disabled

### Application
- **Sentinel command whitelist**: deny-by-default, argument-aware allow list
- **Sentinel blocklist**: explicit rejection of destructive patterns
- **Sentinel runtime identity**: dedicated non-root `sentinel` user (`docker` + `adm` groups only)
- **Docker access scope**: Sentinel tooling is container-allowlisted
- **Telegram auth**: user ID whitelist -- unauthorized users rejected immediately
- **No secrets in git**: `.env` in `.gitignore`, `.env` permissions 600, backup excludes secrets
- **Docker isolation**: OpenClaw runs as non-root user (uid=999) with resource limits

### Agent Isolation
- **Multi-agent separation**: main and work agents have separate workspaces, memory, and tool policies
- **Work agent sandboxing**: agent-scope sandbox prevents cross-contamination
- **No elevated exec**: neither agent can bypass sandbox to run commands on host
- **Channel security**: private DM plus explicitly approved interactive channel chats
- **Tool call caps**: max per task limits prevent runaway loops

### Operational
- **Automated backups**: daily at 03:00, 7-day rotation, secrets excluded
- **Health checks**: multi-check verification script
- **Docker weekly auto-prune**: cron job prevents cache buildup (prevents 37GB+ growth)
- **Logrotate**: Sentinel logs rotated weekly (12 rotations for .jsonl, 4 for .log)
- **Journald capped**: `SystemMaxUse=100M`, `SystemKeepFree=1G`, `MaxRetentionSec=2week`
- **Automatic security updates**: unattended-upgrades enabled
- **Boot checks**: startup health verification before agent activation
- **Change management**: no silent config mutations -- explain, apply, validate, test, report

## Testing

All tests use mocked API calls -- zero API cost during development.

```bash
cd sentinel
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

Test coverage:
- **Command whitelist/blocklist logic** -- dangerous commands rejected
- **Tool schema validation** -- all 9 tools have required function declaration fields
- **Tool execution** -- mocked psutil, Docker, subprocess calls
- **Telegram authorization** -- authorized vs unauthorized user handling
- **Slash command handlers** -- `/start`, `/status`, `/openclaw`, `/security`, `/backup`, `/cost`
- **Config validation** -- missing tokens, provider API keys, user IDs
- **Config parsing edge cases** -- non-numeric/empty/multi-comment user ID parsing
- **Cost tracking** -- append-only events, daily/weekly/monthly aggregation
- **Provider fallback** -- Gemini-to-Anthropic provider switch with conversation history clearing (auto-fallback disabled; tests verify manual override path)

## Quick Start

### Local Development

```bash
# 1. Clone this repo
git clone <repo-url> && cd cldw_Setup

# 2. Validate config files
python3 -c "import json; json.load(open('openclaw/openclaw-config.json'))"

# 3. Verify all config files exist
ls openclaw/config/*.md | wc -l          # Should be 12
ls openclaw/agents/work/*.md | wc -l     # Should be 5

# 4. Run Sentinel tests (no API key needed)
cd sentinel
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

### VPS Validation (Post-Deploy)

```bash
# Core services
cd /root/openclaw
docker compose ps
systemctl status sentinel --no-pager
/root/openclaw-project/infrastructure/health-check.sh

# Job Radar
cd /root/job-radar
docker compose -f docker-compose.job-radar.yml ps
curl -sS http://127.0.0.1:8080/health/full | python3 -m json.tool

# AI brief state
cat /root/.openclaw/workspace/logs/ai-brief-state.json | python3 -m json.tool

# Cost rollup
/root/openclaw-project/infrastructure/update-api-cost-rollup.sh
cat /root/.openclaw/workspace/logs/api-cost-rollup.json | python3 -m json.tool
```

### Manual Telegram Validation

```
/ai_daily_brief status          # Diagnostic check
/ai_daily_brief top5 12h        # Quick brief
/ai_daily_brief_top5            # Compatibility alias (must work)
```

## Key Optimization Decisions

| Decision | Rationale |
|----------|-----------|
| CPX22 over CPX32 | 3 vCPU / 4GB is sufficient -- OpenClaw is I/O bound, not compute bound. Saves ~$5/mo. |
| Gemini Flash as default | Most interactions are routine; Flash is cheaper and faster. |
| 90-min heartbeat | Reduces recurring prompt overhead vs. shorter intervals while maintaining session awareness. |
| SOUL.md ~800 tokens | Sent with every request. 100 extra words x 1000 requests = 100K wasted tokens. |
| contextTokens 65,536 | Hard-caps context window. Prevents runaway input costs from accumulated sessions. |
| contextPruning cache-ttl 30m | Evicts stale tool output after 30 minutes. Keeps context lean without losing recent work. |
| Safeguard compaction | Bounded conversation history. Only `"default"` and `"safeguard"` are valid modes. |
| Zero-cost slash commands | `/status`, `/openclaw`, etc. bypass LLM entirely -- direct tool execution in Python. |
| Loopback gateway binding | No public exposure -- SSH tunnel only. No TLS cert management needed. |
| systemd for Sentinel | Lighter than Docker for a single Python process. Auto-restart on crash. |
| 7-day backup rotation | Prevents disk fill on 80GB NVMe while keeping recovery points. |
| Sentinel provider toggle | Gemini Flash default; Anthropic (Sonnet/Opus) manual-only — auto-fallback disabled. |
| Silent hours 23:00-07:00 | Eliminates proactive API calls during sleep hours. |
| Multi-agent main + work | Separates personal/professional data with sandboxing. Reduces context per agent. |
| 3 cron jobs (AI Brief + ENB 2x) | AI brief on Pro, ENB on Flash. Everything else on-demand. |
| ENB on Flash only | Structured search + summary doesn't need Pro. ~$0.30/month for 2x daily. |
| Sub-agents on Flash | Prevents accidental Pro escalation from sub-agent spawns. |
| imageModel Flash | Image generation uses Flash, not Pro -- significant cost reduction. |
| Docker weekly auto-prune | Prevents multi-GB build cache accumulation on the 80GB disk. |
| Health check TTL 3h | Job Radar external checks cached for 3 hours -- prevents dashboard-driven API spend. |
| Content-based digest dedup | Prevents duplicate Job Radar digests when the same jobs appear across runs. |
| Batch competitor queries | ENB batches 8 competitors into 2-3 Brave calls instead of 8 separate calls. |

## Config Versioning

OpenClaw instruction configs in `openclaw/config/*.md` and `openclaw/agents/work/*.md` include an inline marker:

```md
<!-- config-version: YYYY.MM.DD-scope-description -->
```

Use this marker when reviewing for schema drift across deployments.

## License

Private project. Not licensed for redistribution.
