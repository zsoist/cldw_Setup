# OpenClaw + Sentinel: Cost-Optimized Dual-Bot AI System

A production-ready, budget-conscious deployment of a two-layer AI assistant system on a Hetzner CPX22 VPS. OpenClaw serves as a personal AI gateway accessed via Telegram, while Sentinel acts as an autonomous sysadmin bot managing the infrastructure itself — using a Gemini-first model stack with Anthropic fallbacks for resilience and cost control.

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
                        │  │  ┌─────┐  ┌────────┐  │  │   Flash default    │  │
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

**Zero-Trust API Cost Control:** Every design decision prioritizes minimizing LLM API spend without sacrificing utility. The system targets **$14-23/month total** (VPS + API combined).

## Token Optimization Strategy

This project demonstrates several production-grade techniques for minimizing API costs while maintaining a responsive, useful AI assistant.

### 1. Four-Tier Model Routing (Gemini-first)

| Tier | Model | Use Case | Cost Factor |
|------|-------|----------|-------------|
| **Default** | Gemini 2.5 Flash | Chat, Q&A, reminders, heartbeat, task tracking | ~0.3x |
| **Standard** | Gemini 2.5 Pro | Code generation, research synthesis, AI brief, multi-step tools | ~2x |
| **Premium** | Claude Sonnet 4.6 | "Think harder" tasks and production-grade quality rescue | ~5x |
| **Manual Only** | Claude Opus 4.6 | Architecture decisions, complex analysis | ~60x |

The routing is configured in `openclaw/config/AGENTS.md`. Default traffic stays on Flash, escalates to Pro when needed, then to Sonnet only when quality requires it.

### 2. Prompt Cache Alignment

The heartbeat interval is set to **55 minutes** to keep recurring prompts cache-friendly and limit repeated static prompt cost.

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

No proactive messages are sent between 23:00-07:00 COT. This reduces unnecessary API calls while preserving the single scheduled AI brief run at 07:00.

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

1 scheduled job defined in `openclaw/config/CRON.md`:

| # | Job | Schedule | Agent | Model |
|---|-----|----------|-------|-------|
| 1 | AI Daily Brief Top5 (Previous Day) | 07:00 daily | Main | Gemini Pro |

Everything else runs on-demand via explicit commands.

### 9. AI Daily Brief Capability

The `ai-daily-brief` skill delivers a source-grounded AI briefing with one scheduled daily run and on-demand modes:

- Canonical command: `/ai_daily_brief` (single stable command path).
- Slot/mode selection via arguments:
  - `/ai_daily_brief morning|evening|top5|builder|watchlist|status`
  - `/ai_daily_brief top5 12h|week|month|month YYYY-MM`
- Extended commands:
  - `/ai_daily_brief watchlist add <topic>` / `watchlist remove <topic>` — manage watchlist dynamically
  - `/ai_daily_brief feedback <run_id> <1-5> [comment]` — rate briefs for adaptive tuning
  - `/ai_daily_brief history [n]` — show last N runs with status + cost
  - `/ai_daily_brief diff` — compare last two runs (new/dropped/moved stories)
  - `/ai_daily_brief help` — full command reference in Telegram-friendly format
- Compatibility aliases are also supported:
  - `/ai_daily_brief_morning`, `/ai_daily_brief_evening`, `/ai_daily_brief_top5`, `/ai_daily_brief_builder`, `/ai_daily_brief_watchlist`, `/ai_daily_brief_status`
- Channel context: `/ai_daily_brief@BotName status` strips `@BotName` suffix automatically; approved group/supergroup chats treated identically to DM.
- Execution policy: `/ai_daily_brief*` runs directly in-lane (skill-first), not via mandatory sub-agent spawn.
- Deduplication and update suppression using `/home/node/.openclaw/workspace/logs/ai-brief-state.json`.
- State schema v3: adds `history[]` (last 20 runs), `feedback[]`, `cost_estimate` per run, `last_probe_at` on Brave provider.
- Story output enforces **precise `YYYY-MM-DD` event dates** per story — vague or undated stories are rejected.
- Story output includes **Technical Details** per top story: architecture type, parameter count (or disclosure status), context window, capability delta vs prior version, benchmarks with methodology.
- Brave LLM Context grounding via `https://api.search.brave.com/res/v1/llm/context` with mode-specific token budgets.
- Scheduled automation is limited to one run at `07:00` COT for previous-day top stories.
- All other modes/reports run only on-demand.
- Monthly story archive: `workspace/outputs/summaries/ai-brief-stories-YYYY-MM.json` for trend analysis / thesis research.
- Optional channel routing via `config.output_channel` in state (full brief goes to target channel; originating chat gets ACK/status).
- Channel command setup: set `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` + configure BotFather privacy mode — see `openclaw/config/CHANNELS.md` for step-by-step guide.
- Weighted anti-hype ranking (impact 0.28, credibility 0.22, novelty 0.18, relevance 0.14, freshness 0.10, confidence 0.08).
- Mandatory citations, builder corner, strategic take, and explicit confidence/gaps section.
- Source references must be clickable markdown hyperlinks (`[Outlet](https://...)`).
- Brave LLM Context latency profile tuned for speed+coverage (adaptive 1-2 query fan-out instead of fixed multi-query expansion).
- VPS operational scripts for rollout and smoke-testing:
  - `infrastructure/vps-rollout-aibrief.sh`
  - `infrastructure/aibrief-smoke-test.sh`
  - `infrastructure/set-aibrief-output-channel.sh`
- Rollout hardening:
  - config sync preserves gateway runtime ownership for `/root/.openclaw/openclaw.json`
  - config sync writes `/root/.openclaw/secrets/telegram-default.token` and wires `channels.telegram(.accounts.default).tokenFile` to avoid token drift after config rewrites
  - gateway container receives `TELEGRAM_BOT_TOKEN`/`OPENCLAW_TELEGRAM_TOKEN` and `BRAVE_API_KEY` from `.env`
  - gateway startup now waits for mounted runtime config readiness and auto-clears Telegram webhooks to force polling mode
  - config sync maps DM authorization from `OPENCLAW_TELEGRAM_ALLOW_FROM` (or fallback `SENTINEL_ALLOWED_USERS`) and sets Telegram `dmPolicy=allowlist` automatically when IDs are present
  - config sync supports Telegram command toggles via `OPENCLAW_TELEGRAM_NATIVE_COMMANDS` / `OPENCLAW_TELEGRAM_NATIVE_SKILLS`
  - config sync supports interactive-chat anonymous/channel compatibility via `OPENCLAW_TELEGRAM_INTERACTIVE_ALLOW_ANY_SENDER=1` (sets `groups.<chat>.allowFrom=["*"]` for approved interactive chats)
  - config-only rollout now syncs `infrastructure/docker-compose.yml` into `/root/openclaw` before restart
  - rollout now detects active Telegram webhooks via `getWebhookInfo`, clears them, and restarts gateway before final health validation
  - rollout/smoke diagnostics now read gateway auth token from `/root/.openclaw/openclaw.json` first (env fallback only), preventing false `device token mismatch` checks caused by stale `.env` duplicates
  - smoke test verifies Telegram ingest runtime (`running=true`, `tokenSource!=none`), tokenFile readability, webhook conflict absence, direct in-lane AI brief policy markers in workspace SOUL/AGENTS, and container-visible Brave key
  - smoke test now fails hard when `dmPolicy=pairing` with empty `allowFrom` because DM commands are gated until pairing approval
  - rollout refreshes `/usr/local/sbin/sync-sentinel-env.sh` and `/usr/local/sbin/sync-openclaw-config.sh` from repo before execution to prevent stale helper-script behavior
  - config-only rollout now syncs Sentinel runtime code into `/opt/sentinel` (and refreshes deps when `requirements.txt` changes) to avoid deployment drift between repo and systemd runtime
  - `set-aibrief-output-channel.sh` now also updates `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` when target is numeric chat ID
- Runtime bootstrap files used by command routing are loaded from:
  - `/root/.openclaw/workspace/AGENTS.md`
  - `/root/.openclaw/workspace/SOUL.md`
  - `/root/.openclaw/workspace/TOOLS.md`
  - `/root/.openclaw/workspace/HEARTBEAT.md`

### AI Daily Brief + Gemini VPS Rollout (Fast Path)

```bash
ssh root@YOUR_VPS_IP <<'EOF'
set -euo pipefail
cd /root/openclaw-project
# Pin latest stable OpenClaw build (default in this repo: v2026.2.22)
sed -i '/^OPENCLAW_REF=/d' /root/openclaw/.env
echo "OPENCLAW_REF=v2026.2.22" >> /root/openclaw/.env
# Set keys (Gemini default + Brave grounding)
sed -i '/^GEMINI_API_KEY=/d' /root/openclaw/.env
echo "GEMINI_API_KEY=YOUR_REAL_GEMINI_KEY" >> /root/openclaw/.env
sed -i '/^BRAVE_API_KEY=/d' /root/openclaw/.env
echo "BRAVE_API_KEY=YOUR_REAL_BRAVE_KEY" >> /root/openclaw/.env

# Optional: verify pinned binary sees google provider/models
docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs models list --provider google 2>&1 || true
docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs models auth status --provider google 2>&1 || true

# Rebuild gateway at pinned ref and apply config/skills/docs rollout
cd /root/openclaw
docker compose build --pull openclaw-gateway
docker compose up -d --force-recreate openclaw-gateway
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh

# Verify default + image model routing (nano-banana-pro alias)
docker exec openclaw-openclaw-gateway-1 node /home/node/openclaw/openclaw.mjs models status --json | \
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k:d.get(k) for k in ("defaultModel","fallbacks","imageModel","imageFallbacks","aliases")}, indent=2))'
EOF
```

Smoke test must pass these lines before Telegram command validation:
- `Gateway runtime user can read /home/node/.openclaw/openclaw.json`
- `Runtime config has Telegram auth material (botToken/tokenFile) at channels.telegram(.accounts.default)`
- `Telegram DM allowFrom configured (...)`
- `Telegram ingest runtime is running`
- `Gateway Telegram token source is ...` (not `none`)
- `SOUL policy enforces direct in-lane execution for /ai_daily_brief*`
- `AGENTS policy confirms /ai_daily_brief* does not require sub-agent spawn`
- `Gateway container has BRAVE_API_KEY in environment` (or explicit fallback warning if intentionally unconfigured)
- `Gateway container has GEMINI_API_KEY in environment` (or intentional Claude-only fallback mode)

Manual Telegram validation after rollout:
- send `/ai_daily_brief status`
- send `/ai_daily_brief top5 12h`
- send compatibility alias `/ai_daily_brief_top5` (must return equivalent output path)
- if `OPENCLAW_TELEGRAM_NATIVE_COMMANDS=0`, menu command registration is intentionally disabled; use text commands in approved interactive chat instead.
- run commands from DM with the OpenClaw bot; output channel receives the full brief when configured
- if interactive channel commands are required, ensure channel/supergroup ID is present in `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS`
- note: `/ai_daily_brief_status` is diagnostic and may not mutate `last_run`; `/ai_daily_brief_top5` should create/update `last_run.run_id/status`
- if status reports `provider unconfigured`, re-check `BRAVE_API_KEY` in `/root/openclaw/.env`
- if smoke test shows `BRAVE_API_KEY appears invalid (len=...)`, rotate the key in `/root/openclaw/.env` (no quotes/comments on the same line)
- if Gemini appears unavailable, inspect `docker compose logs --since=120s openclaw-gateway | grep -Ei 'gemini|google|fallback|529|overload'`
- for image-generation routing, `models status --json` should show `imageModel=google/gemini-2.5-pro` and alias `nano-banana-pro`
- if replies show stale internal narration (`Reasoning:`, "I will now...", "I need to verify..."), reset runtime sessions:
  - `cd /root/openclaw-project && ./infrastructure/reset-openclaw-telegram-sessions.sh`
- avoid `openclaw doctor --fix` during AI brief rollout/troubleshooting because it can rewrite channel config and break token wiring

Configure dedicated AI brief channel (optional):
```bash
ssh root@YOUR_VPS_IP <<'EOF'
set -euo pipefail
cd /root/openclaw-project
./infrastructure/set-aibrief-output-channel.sh @dandailybriefAI
EOF
```

## Sentinel: Agentic Sysadmin Bot

Sentinel supports **dual providers**:
- Anthropic (`SENTINEL_PROVIDER=anthropic`, default)
- Google Gemini (`SENTINEL_PROVIDER=google`)

Both providers run the same safe tool-execution loop with shared whitelist controls.

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
| `check_openclaw_health` | Container state + Docker health + recent errors | Read-only |
| `backup_openclaw` | Tar.gz config + workspace | Write (safe location only) |

### Command Whitelist Security Model

The `run_command` tool implements a **dual-layer filter**:

1. **Blocklist check** (runs first): Rejects any command containing dangerous patterns (`rm`, `sudo su`, `apt`, `wget`, `reboot`, `chmod 777`, arbitrary script execution)
2. **Whitelist check** (argument-aware): Only allows explicitly validated command shapes (for example `df -h`, `systemctl status <unit>`, `docker ps`, local-only `curl` health checks)

Unknown commands are rejected by default. This is a deny-by-default posture — even if a novel attack bypasses the blocklist, it still must match a validated safe command form.

### Agentic Loop Implementation

```python
# Simplified flow in sentinel.py
for _ in range(max_iterations):        # Cap at 5 to prevent infinite loops
    response = client.messages.create(
        model="<provider model>",
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
├── CLAUDE-CODE-HANDOFF.md                 # Project state + handoff for next session
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
│   │   ├── CRON.md                        # Cron registry (single daily AI brief job)
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
│   │   │   └── projects/                  # active/ and archived/ subdirs
│   │   ├── outputs/                       # Generated deliverables
│   │   │   ├── summaries/                 # Daily briefs, meeting prep, knowledge capture
│   │   │   ├── reports/                   # Weekly digests, security hygiene, stale items
│   │   │   ├── drafts/                    # In-progress documents
│   │   │   └── exports/                   # Finalized exports
│   │   └── logs/                          # Operational logs
│   │       ├── change-log.md              # Config/infrastructure change record
│   │       ├── cron-job-results.md        # Cron execution log (append-only)
│   │       └── ai-brief-state.json        # Stateful dedupe + slot tracking for AI brief
│   ├── skills/
│   │   ├── ai-daily-brief/SKILL.md        # Canonical AI brief command (scoped top5 + full modes)
│   │   ├── ai-daily-brief-*/SKILL.md      # Compatibility alias shims for /ai_daily_brief_* commands
│   │   ├── daily-briefing/SKILL.md        # Morning planning briefing (Gemini Flash, scheduled)
│   │   ├── research-assistant/SKILL.md    # Deep research (Gemini Pro, on-demand)
│   │   └── task-tracker/SKILL.md          # Task management (Gemini Flash, triggered)
│   ├── memory/                            # Daily + weekly log storage
│   │   ├── weekly/                        # Weekly review summaries
│   │   └── (YYYY-MM-DD.md files)          # Auto-generated daily logs
│   └── openclaw-config.json               # Gateway runtime config (schema-valid for pinned OpenClaw)
├── sentinel/                              # Sysadmin Bot (Anthropic/Gemini provider abstraction + tool use)
│   ├── sentinel.py                        # Agentic loop with tool chaining
│   ├── tools.py                           # 8 tools + whitelist/blocklist security
│   ├── config.py                          # Dataclass config with validation
│   ├── telegram_handler.py                # Telegram interface + auth
│   ├── requirements.txt                   # Python dependencies
│   ├── sentinel.service                   # systemd unit file
│   └── tests/
│       ├── conftest.py                    # Shared fixtures (mocked provider clients)
│       ├── test_tools.py                  # Whitelist, tool dispatch, Docker mocks
│       └── test_telegram.py               # Auth, commands, message handling
├── infrastructure/                        # Deployment & operations
│   ├── Dockerfile                         # OpenClaw container (node:22-bookworm + pnpm build)
│   ├── docker-compose.yml                 # Resource limits tuned for CPX22
│   ├── env.template                       # Secret placeholders (never committed)
│   ├── deploy.sh                          # One-shot VPS deployment
│   ├── secure.sh                          # UFW + fail2ban + SSH hardening
│   ├── sync-sentinel-env.sh               # Syncs /root/openclaw/.env -> /etc/sentinel/sentinel.env
│   ├── sync-openclaw-config.sh            # Renders /root/.openclaw/openclaw.json from /root/openclaw/.env
│   ├── validate-placeholders.sh           # Validates required secrets are non-placeholder
│   ├── backup.sh                          # Automated backup (7-day rotation, no secrets)
│   ├── restore.sh                         # Interactive restore from backup
│   ├── health-check.sh                    # Multi-check system health verification
│   ├── aibrief-smoke-test.sh              # AI brief health + token + state smoke test
│   ├── vps-rollout-aibrief.sh             # Config-only AI brief rollout/update path
│   ├── merge-ai-brief-state.sh            # Template->runtime state merge (preserve history/routing)
│   ├── set-aibrief-output-channel.sh      # Configure AI brief output channel in state
│   ├── reset-telegram-offset.sh           # Reset stale Telegram update offsets + restart gateway
│   └── ssh-config-snippet                 # Mac SSH config with tunnel
└── docs/
    ├── setup/
    │   ├── model-routing-policy.md        # Detailed model routing reference
    │   └── performance-tuning.md          # API cost + responsiveness tuning
    ├── security/
    │   ├── access-boundaries.md           # Agent/channel access matrix
    │   ├── openclaw-hardening.md          # Gateway security hardening practices
    │   └── secrets-rotation.md            # Secret rotation schedule and procedure
    ├── playbooks/
    │   ├── ai-daily-brief.md              # AI brief pipeline + quality gates
    │   ├── daily-planning.md              # Daily brief playbook
    │   ├── personal-weekly-review.md      # Weekly review playbook
    │   ├── meeting-prep.md                # Meeting preparation playbook
    │   └── decision-log-template.md       # Decision record format
    ├── templates/
    │   ├── ai-daily-brief-template.md     # AI brief output format
    │   ├── research-summary-template.md   # Research output format
    │   ├── brief-template.md              # Executive brief format
    │   └── sop-template.md                # Standard operating procedure format
    ├── research/
    │   └── job-search-automation.md       # Job search capabilities + implementation plan
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
| LLM APIs (Gemini-first + Anthropic fallback) | $6-15 |
| **Total** | **$14-23** |

### Per-Interaction Cost Breakdown

| Interaction Type | Model | Estimated Cost |
|-----------------|-------|----------------|
| Simple Q&A / chat | Gemini 2.5 Flash | ~$0.0005-0.001 |
| Heartbeat cycle | Gemini 2.5 Flash | ~$0.0003-0.0008 |
| Daily planning briefing | Gemini 2.5 Flash | ~$0.001-0.002 |
| AI Daily Brief (morning/evening) | Gemini 2.5 Pro | ~$0.01-0.03 |
| Research deep dive | Gemini 2.5 Pro | ~$0.01-0.03 |
| Code generation | Gemini 2.5 Pro | ~$0.015-0.05 |
| Sentinel status check | Gemini 2.5 Flash | ~$0.001-0.003 |
| Complex analysis | Opus 4.6 | $0.10-0.30 |

With ~50-100 daily interactions (mostly Flash), monthly API cost stays within the $6-15 target range.

## Security Model

### Network
- **UFW**: deny-all inbound except SSH (port 22)
- **OpenClaw gateway**: bound to loopback — accessible only via SSH tunnel
- **fail2ban**: 3 failed attempts = 1 hour ban
- **SSH**: key-only authentication, password auth disabled

### Application
- **Sentinel command whitelist**: deny-by-default, argument-aware allow list
- **Sentinel blocklist**: explicit rejection of destructive patterns
- **Sentinel runtime identity**: dedicated non-root `sentinel` user (`docker` + `adm` groups only)
- **Docker access scope**: Sentinel tooling is container-allowlisted (`openclaw-openclaw-gateway-1`)
- **Telegram auth**: user ID whitelist — unauthorized users get rejected immediately
- **No secrets in git**: `.env` in `.gitignore`, backup excludes `.env`/`.pem`/`.key`
- **Docker isolation**: OpenClaw runs as non-root user in container with resource limits

### Agent Isolation
- **Multi-agent separation**: main and work agents have separate workspaces, memory, and tool policies
- **Work agent sandboxing**: agent-scope sandbox prevents cross-contamination of personal/professional data
- **No elevated exec**: neither agent can bypass sandbox to run commands on host
- **Channel security**: private DM plus explicitly approved interactive channel/supergroup chats, sender allowlist enforced
- **Tool call caps**: max 10 per task (main), max 8 per task (work) — prevents runaway loops

### Operational
- **Automated backups**: daily at 03:00, 7-day rotation, secrets excluded from tarballs
- **Health checks**: multi-check verification script (Docker + gateway health + fallback endpoint + security + disk/memory + backups)
- **Deploy ownership alignment**: `/root/.openclaw` ownership is aligned to container `openclaw` UID/GID after image build
- **Rate limiting**: Sentinel enforces per-user request windows to reduce abuse/API burn
- **Tamper-evident audit trail**: tool execution events are hash-chained in `/var/log/sentinel/audit.log`
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
- **Tool schema validation** — all 8 tools have required Anthropic and Gemini function declaration fields
- **Tool execution** — mocked psutil, Docker, subprocess calls
- **Telegram authorization** — authorized vs unauthorized user handling
- **Command handlers** — /start, /status, /openclaw, /security, /backup
- **Config validation** — missing tokens, provider API keys, user IDs
- **Message handling** — free-text routing through the agentic loop
- **Config parsing edge cases** — non-numeric/empty/multi-comment user ID parsing

## Config Versioning

OpenClaw instruction configs in `openclaw/config/*.md` and `openclaw/agents/work/*.md` include an inline marker:

```md
<!-- config-version: 2026.02.21-main-hardening -->
```

Use this marker when reviewing for schema drift across branches or deployments.

## Quick Start (Local Development)

```bash
# 1. Clone this repo
git clone <repo-url> && cd cldw_Setup

# 2. Validate config files
python3 -c "import json; json.load(open('openclaw/openclaw-config.json'))"

# 3. Check SOUL.md word count (must be < 500)
wc -w openclaw/config/SOUL.md

# 4. Verify all config files exist
ls openclaw/config/*.md | wc -l          # Should be 12
ls openclaw/agents/work/*.md | wc -l     # Should be 5

# 5. Verify workspace content
ls openclaw/workspace/personal/goals.md openclaw/workspace/business/goals-okrs.md

# 6. Run Sentinel tests (no API key needed)
cd sentinel
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v

# 7. When ready to deploy, see docs/DEPLOYMENT.md
```

## VPS Validation (Post-Deploy)

```bash
cd /root/openclaw
docker compose ps
systemctl status sentinel --no-pager
/root/openclaw-project/infrastructure/health-check.sh
```

Notes:
- OpenClaw is a WebSocket gateway; root HTTP probes can be misleading on some builds.
- Treat Docker health (`healthy`) and `health-check.sh` as the source of truth.

## Key Optimization Decisions Explained

| Decision | Rationale |
|----------|-----------|
| CPX22 over CPX32 | 3 vCPU / 4GB is sufficient — OpenClaw is I/O bound (API calls), not compute bound. Saves ~$5/mo. |
| Gemini Flash as default | Most interactions are routine; Flash is lower cost and faster for baseline flows. |
| 55-min heartbeat | Keeps recurring prompt overhead bounded with cache-friendly cadence. |
| SOUL.md < 500 words | Sent with every request. 100 extra words x 1000 requests = 100K wasted tokens. |
| Safeguard compaction | Prevents long conversations from inflating input token costs. |
| Loopback gateway binding | No public exposure — SSH tunnel only. Eliminates need for TLS cert management. |
| systemd for Sentinel | Lighter than Docker for a single Python process. Auto-restart on crash. |
| 7-day backup rotation | Prevents disk fill on 80GB NVMe while keeping a week of recovery points. |
| Sentinel provider toggle | Default Anthropic path remains stable; Google provider is available for redundancy/testing. |
| Silent hours (23:00-07:00) | Reduces proactive API calls while preserving the 07:00 scheduled AI brief run. |
| Multi-agent (main + work) | Separates personal/professional data, enables sandboxing, reduces context per agent. |
| Agent-scope sandbox for work | Isolates professional data without session-scope overhead. |
| No elevated exec | Sandboxing is meaningless if agents can bypass it via host execution. |
| Channel allowlist + approved interactive chats only | Group chats are the highest prompt injection surface area; only explicit interactive chat IDs are allowed. |
| 1 cron job, Gemini Pro for AI brief synthesis | Only one automated run is enabled (07:00 previous-day top stories); everything else is on-demand. |
| Read/notify before act | Cron jobs that auto-execute risky actions compound errors at scale. |
| Deep research opt-in only | Auto-triggered deep research is the fastest way to blow through API budget. |
| Save reusable research to docs/ | Prevents redundant web searches for the same topic. |
| Workspace content separation | personal/ vs business/ vs outputs/ vs logs/ prevents cross-contamination. |

## License

Private project. Not licensed for redistribution.
