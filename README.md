# OpenClaw + Sentinel: Cost-Optimized Dual-Bot AI System

A production-ready, budget-conscious deployment of a two-layer AI assistant system on a Hetzner CPX22 VPS. OpenClaw serves as a personal AI gateway accessed via Telegram, while Sentinel acts as an autonomous sysadmin bot managing the infrastructure itself — both powered by the Anthropic Claude API with aggressive cost optimization.

## Architecture

```
                        ┌───────────────────────────────────────────────────────┐
                        │              Hetzner CPX22 VPS                        │
                        │         Ubuntu 24.04 LTS | 3 vCPU | 4GB RAM          │
                        │                                                       │
  Telegram ────────────>│  ┌───────────────────────┐  ┌─────────────────────┐  │
  (OpenClaw Bot)        │  │   Docker Container     │  │   systemd service   │  │
                        │  │                        │  │                     │  │
                        │  │   OpenClaw Gateway     │  │   Sentinel Bot      │  │
                        │  │   Port 18789 (lo)      │  │   Python + SDK      │  │
                        │  │                        │  │                     │  │
                        │  │  ┌─────┐  ┌────────┐  │  │   Haiku 4.5 only   │  │
                        │  │  │main │  │  work  │  │  │   8 tool functions  │  │
  Telegram ────────────>│  │  │agent│  │ agent  │  │  │   Strict whitelist  │  │
  (Sentinel Bot)        │  │  │     │  │sandbox │  │  └─────────────────────┘  │
                        │  │  └─────┘  └────────┘  │                           │
                        │  └───────────────────────┘                           │
                        │                                                       │
  SSH Tunnel ──────────>│  UFW (SSH only) + fail2ban + key-only auth           │
  (Mac Client)          └───────────────────────────────────────────────────────┘
```

### Design Philosophy

**Gateway Runtime Model:** OpenClaw is a persistent gateway process — not just a chatbot. It maintains long-running channel connections, dispatches messages to agent runtimes, and manages tool execution. This framing drives decisions about security, availability, and remote access.

**Multi-Agent Architecture:** Two agent profiles run within the gateway — `main` (personal) and `work` (professional). Each has separate workspace files, memory, tool policies, and risk profiles. The work agent runs in an agent-scope sandbox for data isolation.

**Tenant-Landlord Model:** OpenClaw is the "tenant" — it handles user-facing tasks (research, scheduling, task management) inside a resource-constrained Docker container. Sentinel is the "landlord" — it monitors the system, manages Docker, runs security audits, and creates backups. Neither can interfere with the other, and Sentinel has a strict command whitelist preventing destructive operations.

**Zero-Trust API Cost Control:** Every design decision prioritizes minimizing LLM API spend without sacrificing utility. The system targets **$18-33/month total** (VPS + API combined).

## Token Optimization Strategy

This project demonstrates several production-grade techniques for minimizing Anthropic API costs while maintaining a responsive, useful AI assistant.

### 1. Three-Tier Model Routing

| Tier | Model | Use Case | Cost Factor |
|------|-------|----------|-------------|
| **Default** | Claude Haiku 4.5 | Chat, Q&A, reminders, heartbeat, task tracking | 1x (baseline) |
| **Escalation** | Claude Sonnet 4.5 | Code generation, research synthesis, multi-step tools | ~5x |
| **Manual Only** | Claude Opus 4.6 | Architecture decisions, complex analysis | ~60x |

The routing is configured in `openclaw/config/AGENTS.md`. By defaulting to Haiku for ~80% of interactions and only escalating when synthesis or complex reasoning is required, the system reduces average per-interaction cost by an estimated 10-15x compared to running Sonnet as default.

### 2. Prompt Cache Alignment

Anthropic's prompt caching has a **60-minute TTL**. The heartbeat interval is set to **55 minutes** — just under the cache expiry. This ensures the system prompt (SOUL.md, ~400 words) remains cached across heartbeat cycles, avoiding redundant input token charges on the static portion of every request.

```
Cache TTL:     |-------- 60 min --------|-------- 60 min --------|
Heartbeat:     |------ 55 min ------|------ 55 min ------|------
                     ↑ cache warm         ↑ cache warm
```

### 3. System Prompt Engineering for Token Efficiency

`SOUL.md` is capped at **500 words** (target ~400). Every word in this file is sent with every API request, so the cost compounds across thousands of interactions. The prompt is:

- **Structured for LLM parsing** — headers, bullet points, no prose
- **Specificity-balanced** — enough context to be useful, not so much it wastes tokens
- **Priority-ordered** — most important rules first (early attention gets weighted more)

### 4. Conversation Compaction

The OpenClaw config uses `"compaction": {"mode": "safeguard"}`, which automatically compresses long conversation histories. Without compaction, a 50-message conversation could consume 10,000+ input tokens per new request. With safeguard compaction, the effective context stays bounded.

### 5. Silent Hours Optimization

No proactive messages are sent between 23:00-07:00 COT. This eliminates ~33% of potential heartbeat cycles, directly reducing API calls. The heartbeat task list is priority-ordered so the cheapest checks (unread messages, pending tasks) run first, and expensive operations (web search for news) only trigger during morning briefing windows.

### 6. Response Token Caps

| Component | Max Tokens |
|-----------|-----------|
| OpenClaw responses | 2048 |
| Sentinel responses | 1024 |
| Bot instruction | "Keep under 300 words" |

Capping response tokens prevents runaway generation costs. Sentinel is deliberately limited to 1024 since infrastructure status reports are inherently concise.

### 7. Resource-Constrained Container Limits

The Docker Compose configuration enforces hard resource limits tuned for the CPX22's 3 vCPU / 4GB RAM:

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

This leaves 1 vCPU and ~1.5GB RAM for Sentinel + OS overhead, preventing either service from starving the other.

### 8. Cron Job Architecture

10 scheduled jobs defined in `openclaw/config/CRON.md`, split between personal and business:

| # | Job | Schedule | Agent | Model |
|---|-----|----------|-------|-------|
| 1 | Daily Planning Brief | 07:00 daily | Main | Haiku |
| 2 | EOD Review | 20:00 daily | Main | Haiku |
| 3 | Weekly Personal Review | Sun 20:00 | Main | Haiku |
| 4 | Calendar Prep Watch | Every 4h | Main | Haiku |
| 5 | Knowledge Capture | Mon/Wed/Fri 19:00 | Main | Haiku |
| 6 | Business Daily Snapshot | Weekdays 08:00 | Work | Haiku |
| 7 | Meeting Prep Generator | Hourly (work hours) | Work | Haiku/Sonnet |
| 8 | Pipeline Stale Check | Weekdays 16:00 | Work | Haiku |
| 9 | Weekly KPI Digest | Fri 17:00 | Work | Haiku |
| 10 | Security Hygiene | Mon 09:00 | Work | Haiku |

Every job follows the read → analyze → notify pattern. Deep research and destructive actions never run automatically.

## Sentinel: Agentic Sysadmin Bot

Sentinel is built on the **Anthropic SDK's tool_use pattern** — a production implementation of the agentic loop where Claude decides which tools to invoke, processes results, and iterates until it can provide a final answer.

### Tool Architecture

8 tools with strict safety controls:

| Tool | Description | Safety |
|------|-------------|--------|
| `system_stats` | CPU, RAM, disk, uptime | Read-only |
| `docker_status` | List all containers | Read-only |
| `docker_restart` | Restart a container | Requires confirmation in prompt |
| `docker_logs` | Tail container logs (max 200 lines) | Read-only, truncated |
| `run_command` | Execute shell command | **Whitelist-only**, blocklist enforced |
| `check_security` | UFW, fail2ban, open ports audit | Read-only |
| `check_openclaw_health` | Container + HTTP health | Read-only |
| `backup_openclaw` | Tar.gz config + workspace | Write (safe location only) |

### Command Whitelist Security Model

The `run_command` tool implements a **dual-layer filter**:

1. **Blocklist check** (runs first): Rejects any command containing dangerous patterns (`rm`, `sudo su`, `apt`, `wget`, `reboot`, `chmod 777`, arbitrary script execution)
2. **Whitelist check** (prefix-based): Only allows commands starting with known-safe prefixes (`df`, `free`, `uptime`, `ufw status`, `docker ps`, etc.)

Unknown commands are rejected by default. This is a deny-by-default security posture — even if a novel attack bypasses the blocklist, it still needs to match a whitelisted prefix.

### Agentic Loop Implementation

```python
# Simplified flow in sentinel.py
for _ in range(max_iterations):        # Cap at 5 to prevent infinite loops
    response = client.messages.create(
        model="claude-haiku-4-5",
        tools=TOOLS,
        messages=history,
    )
    if response.stop_reason == "tool_use":
        # Execute tool, feed result back, loop
        result = execute_tool(block.name, block.input)
        history.append(tool_result)
        continue
    else:
        return text_response            # Final answer
```

The loop allows Claude to chain multiple tool calls (e.g., check system stats -> check Docker status -> format report) without human intervention, while the iteration cap prevents runaway API calls.

## Project Structure

```
.
├── README.md                              # This file
├── CLAUDE-CODE-HANDOFF.md                 # Original project specification
├── openclaw/                              # OpenClaw Gateway configuration
│   ├── config/                            # Main agent ("Claw") workspace files
│   │   ├── SOUL.md                        # Orchestrator identity + delegation protocol
│   │   ├── USER.md                        # Daniel's profile + preferences
│   │   ├── AGENTS.md                      # Sub-agent registry + model routing
│   │   ├── TOOLS.md                       # Tool policy + permissions + operating rules
│   │   ├── HEARTBEAT.md                   # Proactive schedule + EOD/weekly logs
│   │   ├── MEMORY.md                      # Persistent memory + daily log system
│   │   ├── IDENTITY.md                    # Persona tone + style
│   │   ├── BOOTSTRAP.md                   # First-run behavior (retires after setup)
│   │   ├── BOOT.md                        # Startup health checks (runs every boot)
│   │   ├── CRON.md                        # Full cron job registry (10 jobs)
│   │   ├── CHANNELS.md                    # Channel security policy + allowlists
│   │   └── SANDBOX.md                     # Sandbox policy + agent isolation rules
│   ├── agents/
│   │   └── work/                          # Work agent ("Claw Work") — sandboxed
│   │       ├── SOUL.md                    # Professional-only scope, stricter rules
│   │       ├── TOOLS.md                   # Restricted tool policy
│   │       ├── USER.md                    # Work-context profile only
│   │       ├── MEMORY.md                  # Work-specific memory (isolated)
│   │       └── HEARTBEAT.md               # Work-hours schedule (08:00-20:00)
│   ├── workspace/                         # Runtime workspace content
│   │   ├── personal/                      # Personal context (main agent)
│   │   │   ├── goals.md                   # Quarterly/monthly goals + success criteria
│   │   │   ├── routines.md                # Daily/weekly routines + reminder prefs
│   │   │   └── projects/                  # Personal project files
│   │   ├── business/                      # Professional context (work agent)
│   │   │   ├── goals-okrs.md              # Business objectives + key results
│   │   │   ├── operating-rules.md         # Work boundaries + quality standards
│   │   │   └── projects/active|archived/  # Business project files
│   │   ├── outputs/                       # Generated deliverables
│   │   │   ├── summaries/                 # Daily briefs, meeting prep, knowledge capture
│   │   │   ├── reports/                   # Weekly digests, security hygiene, stale items
│   │   │   ├── drafts/                    # In-progress documents
│   │   │   └── exports/                   # Finalized exports
│   │   └── logs/                          # Operational logs
│   │       ├── change-log.md              # Config/infrastructure change record
│   │       └── cron-job-results.md        # Cron execution log (append-only)
│   ├── skills/
│   │   ├── daily-briefing/SKILL.md        # Morning briefing (Haiku, scheduled)
│   │   ├── research-assistant/SKILL.md    # Deep research (Sonnet, on-demand)
│   │   └── task-tracker/SKILL.md          # Task management (Haiku, triggered)
│   ├── memory/                            # Daily + weekly log storage
│   │   ├── weekly/                        # Weekly review summaries
│   │   └── (YYYY-MM-DD.md files)          # Auto-generated daily logs
│   └── openclaw-config.json               # Gateway config (multi-agent + sandbox)
├── sentinel/                              # Sysadmin Bot (Anthropic SDK + tool_use)
│   ├── sentinel.py                        # Agentic loop with tool chaining
│   ├── tools.py                           # 8 tools + whitelist/blocklist security
│   ├── config.py                          # Dataclass config with validation
│   ├── telegram_handler.py                # Telegram interface + auth
│   ├── requirements.txt                   # Python dependencies
│   ├── sentinel.service                   # systemd unit file
│   └── tests/
│       ├── conftest.py                    # Shared fixtures (mocked Anthropic client)
│       ├── test_tools.py                  # Whitelist, tool dispatch, Docker mocks
│       └── test_telegram.py               # Auth, commands, message handling
├── infrastructure/                        # Deployment & operations
│   ├── Dockerfile                         # OpenClaw container (node:20-slim)
│   ├── docker-compose.yml                 # Resource limits tuned for CPX22
│   ├── env.template                       # Secret placeholders (never committed)
│   ├── deploy.sh                          # One-shot VPS deployment
│   ├── secure.sh                          # UFW + fail2ban + SSH hardening
│   ├── backup.sh                          # Automated backup (7-day rotation, no secrets)
│   ├── restore.sh                         # Interactive restore from backup
│   ├── health-check.sh                    # 8-point system health verification
│   └── ssh-config-snippet                 # Mac SSH config with tunnel
└── docs/
    ├── setup/
    │   └── model-routing-policy.md        # Detailed model routing reference
    ├── security/
    │   └── access-boundaries.md           # Agent/channel access matrix
    ├── playbooks/
    │   ├── daily-planning.md              # Daily brief playbook
    │   ├── personal-weekly-review.md      # Weekly review playbook
    │   ├── meeting-prep.md                # Meeting preparation playbook
    │   └── decision-log-template.md       # Decision record format
    ├── templates/
    │   ├── research-summary-template.md   # Research output format
    │   ├── brief-template.md              # Executive brief format
    │   └── sop-template.md                # Standard operating procedure format
    ├── research/                           # Saved reusable research (date-stamped)
    ├── DEPLOYMENT.md                      # Step-by-step deployment guide
    ├── COST-MANAGEMENT.md                 # Budget tracking + optimization tips
    ├── TROUBLESHOOTING.md                 # Common issues + recovery procedures
    └── PHASE3-CHECKLIST.md                # Go-live verification checklist
```

## Cost Projections

### Monthly Operating Cost

| Component | Cost |
|-----------|------|
| Hetzner CPX22 (3 vCPU, 4GB, 80GB NVMe) | ~$8 |
| Anthropic API (Haiku-dominant mix) | $10-25 |
| **Total** | **$18-33** |

### Per-Interaction Cost Breakdown

| Interaction Type | Model | Estimated Cost |
|-----------------|-------|----------------|
| Simple Q&A / chat | Haiku 4.5 | ~$0.001 |
| Heartbeat cycle | Haiku 4.5 | ~$0.0005 |
| Daily briefing | Haiku 4.5 | ~$0.002 |
| Research deep dive | Sonnet 4.5 | $0.02-0.05 |
| Code generation | Sonnet 4.5 | $0.03-0.08 |
| Sentinel status check | Haiku 4.5 | ~$0.002 |
| Complex analysis | Opus 4.6 | $0.10-0.30 |

With ~50-100 daily interactions (mostly Haiku), monthly API cost stays well under $25.

## Security Model

### Network
- **UFW**: deny-all inbound except SSH (port 22)
- **OpenClaw gateway**: bound to loopback — accessible only via SSH tunnel
- **fail2ban**: 3 failed attempts = 1 hour ban
- **SSH**: key-only authentication, password auth disabled

### Application
- **Sentinel command whitelist**: deny-by-default, prefix-based allow list
- **Sentinel blocklist**: explicit rejection of destructive patterns
- **Telegram auth**: user ID whitelist — unauthorized users get rejected immediately
- **No secrets in git**: `.env` in `.gitignore`, backup excludes `.env`/`.pem`/`.key`
- **Docker isolation**: OpenClaw runs as non-root user in container with resource limits

### Agent Isolation
- **Multi-agent separation**: main and work agents have separate workspaces, memory, and tool policies
- **Work agent sandboxing**: agent-scope sandbox prevents cross-contamination of personal/professional data
- **No elevated exec**: neither agent can bypass sandbox to run commands on host
- **Channel security**: private DM only, no group chats, sender allowlist enforced
- **Tool call caps**: max 10 per task (main), max 8 per task (work) — prevents runaway loops

### Operational
- **Automated backups**: daily at 03:00, 7-day rotation, secrets excluded from tarballs
- **Health checks**: 8-point verification script (Docker, HTTP, disk, memory, UFW, backups)
- **Boot checks**: startup health verification before agent activation (BOOT.md)
- **Automatic security updates**: unattended-upgrades enabled
- **Change management**: no silent config mutations — explain, apply, validate, test, report
- **Post-config checks**: security audit + health check required after sandbox or channel changes
- **Cron discipline**: all jobs read/notify first, deep research opt-in only, results logged

## Testing

All tests use mocked API calls — zero API cost during development.

```bash
cd sentinel
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

Test coverage includes:
- **Command whitelist/blocklist logic** — ensures dangerous commands are rejected
- **Tool schema validation** — all 8 tools have required Anthropic API fields
- **Tool execution** — mocked psutil, Docker, subprocess calls
- **Telegram authorization** — authorized vs unauthorized user handling
- **Command handlers** — /start, /status, /openclaw, /security, /backup
- **Config validation** — missing tokens, API keys, user IDs
- **Message handling** — free-text routing through the agentic loop

## Quick Start (Local Development)

```bash
# 1. Clone this repo
git clone <repo-url> && cd cldw_Setup

# 2. Validate config files
python3 -c "import json; json.load(open('openclaw/openclaw-config.json'))"

# 3. Check SOUL.md word count (must be < 500)
wc -w openclaw/config/SOUL.md

# 4. Run Sentinel tests (no API key needed)
cd sentinel
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v

# 5. When ready to deploy, see docs/DEPLOYMENT.md
```

## Key Optimization Decisions Explained

| Decision | Rationale |
|----------|-----------|
| CPX22 over CPX32 | 3 vCPU / 4GB is sufficient — OpenClaw is I/O bound (API calls), not compute bound. Saves ~$5/mo. |
| Haiku as default | 80%+ of interactions are simple enough for Haiku. Sonnet escalation only when needed. |
| 55-min heartbeat | Aligns with Anthropic's 60-min prompt cache TTL — maximizes cache hits. |
| SOUL.md < 500 words | Sent with every request. 100 extra words x 1000 requests = 100K wasted tokens. |
| Safeguard compaction | Prevents long conversations from inflating input token costs. |
| Loopback gateway binding | No public exposure — SSH tunnel only. Eliminates need for TLS cert management. |
| systemd for Sentinel | Lighter than Docker for a single Python process. Auto-restart on crash. |
| 7-day backup rotation | Prevents disk fill on 80GB NVMe while keeping a week of recovery points. |
| Sentinel on Haiku only | Sysadmin tasks (status, logs, restart) never need Sonnet-level reasoning. |
| Silent hours (23:00-07:00) | Eliminates ~33% of heartbeat API calls with zero utility loss. |
| Multi-agent (main + work) | Separates personal/professional data, enables sandboxing, reduces context per agent. |
| Agent-scope sandbox for work | Isolates professional data without session-scope overhead. |
| No elevated exec | Sandboxing is meaningless if agents can bypass it via host execution. |
| Channel allowlist + no groups | Group chats are the highest prompt injection surface area. |
| 10 cron jobs, all Haiku default | Scheduled tasks are repetitive — never worth Sonnet unless strategic depth needed. |
| Read/notify before act | Cron jobs that auto-execute risky actions compound errors at scale. |
| Deep research opt-in only | Auto-triggered deep research is the fastest way to blow through API budget. |
| Save reusable research to docs/ | Prevents redundant web searches for the same topic. |
| Workspace content separation | personal/ vs business/ vs outputs/ vs logs/ prevents cross-contamination. |

## License

Private project. Not licensed for redistribution.
