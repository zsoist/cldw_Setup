# CLAUDE CODE HANDOFF: OpenClaw + Sysadmin Bot — Full Local Build

> **INSTRUCTIONS FOR CLAUDE CODE (Opus 4.6):**
> This is a complete project specification. The human wants to build everything locally on their Mac BEFORE deploying to a Hetzner CPX32 VPS. The goal is $0 in API costs during the build phase — all LLM API spending happens only after deployment when the system is verified working.
>
> **Read this entire document before writing any code.** Execute phases in order. Ask the human for input only where marked [NEEDS INPUT]. Do not skip phases.

---

## PROJECT CONTEXT

### Who is the human
- Name: Daniel
- Role: Senior Associate at Dialectica (TMT consulting), pursuing MS in AI at Universidad de Los Andes (Bogotá)
- Technical level: Comfortable with terminal, Python, basic DevOps. Not a full-time developer.
- Has: Hetzner Cloud account (not yet provisioned), Mac (local machine), familiarity with Claude ecosystem

### What we're building
A two-bot system on a Hetzner CPX32 VPS (4 vCPU, 8GB RAM, 160GB NVMe, €10.99/mo):

1. **OpenClaw Gateway** — Personal AI assistant running 24/7 in Docker, accessed via Telegram. Handles day-to-day tasks: calendar, research, file management, reminders, web browsing.

2. **Sysadmin Bot ("Sentinel")** — Custom Python bot built on the Anthropic SDK. Manages the VPS infrastructure itself: Docker container management, system monitoring, security audits, log analysis. Also accessed via Telegram (separate bot). Acts as the "landlord" while OpenClaw is the "tenant."

### Architecture diagram
```
┌─────────────────────────────────────────────────────────┐
│                   Hetzner CPX32 VPS                      │
│                  Ubuntu 24.04 LTS                        │
│                                                          │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │   Docker Container   │  │   systemd service        │  │
│  │                      │  │                           │  │
│  │   OpenClaw Gateway   │  │   Sentinel (Sysadmin)    │  │
│  │   Port 18789 (lo)    │  │   Python + Anthropic SDK │  │
│  │                      │  │                           │  │
│  │   Telegram Bot #1    │  │   Telegram Bot #2         │  │
│  │   LLM: Haiku/Sonnet  │  │   LLM: Haiku only        │  │
│  └─────────────────────┘  └──────────────────────────┘  │
│                                                          │
│  Tailscale (optional) ←── SSH Tunnel ──→ Mac (Daniel)   │
└─────────────────────────────────────────────────────────┘
```

### File structure to create
```
~/openclaw-project/
├── README.md                          # Project overview
├── openclaw/                          # OpenClaw configuration files
│   ├── config/
│   │   ├── SOUL.md                    # Bot personality + rules
│   │   ├── USER.md                    # Daniel's profile for the bot
│   │   ├── AGENTS.md                  # Agent routing configuration
│   │   ├── HEARTBEAT.md              # Proactive schedule
│   │   └── MEMORY.md                 # Initial memory seeds
│   ├── skills/                        # Custom skills
│   │   ├── daily-briefing/
│   │   │   └── SKILL.md
│   │   ├── research-assistant/
│   │   │   └── SKILL.md
│   │   └── task-tracker/
│   │       └── SKILL.md
│   └── openclaw-config.json           # openclaw.json template
├── sentinel/                          # Sysadmin bot
│   ├── sentinel.py                    # Main bot code
│   ├── tools.py                       # Tool definitions (SSH, Docker, monitoring)
│   ├── config.py                      # Configuration management
│   ├── telegram_handler.py            # Telegram bot interface
│   ├── requirements.txt               # Python dependencies
│   ├── sentinel.service               # systemd unit file
│   ├── tests/
│   │   ├── test_tools.py              # Unit tests with mocked API
│   │   ├── test_telegram.py           # Telegram handler tests
│   │   └── conftest.py                # Pytest fixtures
│   └── README.md                      # Sentinel-specific docs
├── infrastructure/                    # Deployment scripts
│   ├── Dockerfile                     # OpenClaw Docker image
│   ├── docker-compose.yml             # Docker Compose config
│   ├── env.template                   # .env template (no secrets)
│   ├── deploy.sh                      # One-shot deployment script
│   ├── secure.sh                      # Security hardening script
│   ├── backup.sh                      # Automated backup script
│   ├── restore.sh                     # Restore from backup
│   ├── health-check.sh               # System health verification
│   └── ssh-config-snippet             # SSH config for Mac
├── docs/
│   ├── DEPLOYMENT.md                  # Step-by-step deployment guide
│   ├── COST-MANAGEMENT.md            # LLM cost tracking + limits
│   ├── TROUBLESHOOTING.md            # Common issues + fixes
│   └── PHASE3-CHECKLIST.md           # Go-live checklist
└── .gitignore
```

---

## PHASE 1: Project Scaffolding

### 1.1 Create the directory structure

Create all directories and placeholder files as shown above. Initialize a git repo.

```bash
cd ~
mkdir -p openclaw-project/{openclaw/{config,skills/{daily-briefing,research-assistant,task-tracker}},sentinel/tests,infrastructure,docs}
cd openclaw-project
git init
```

### 1.2 Create .gitignore

```gitignore
# Secrets — NEVER commit
.env
*.pem
*.key
sentinel/config_local.py

# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
node_modules/

# OS
.DS_Store
Thumbs.db

# Backups
*.tar.gz
```

---

## PHASE 2: OpenClaw Configuration Files

These are the markdown/JSON files that define the bot's behavior. They get copied into the VPS's `~/.openclaw/` directory at deployment time.

### 2.1 SOUL.md

**This is the most critical file. It is sent with EVERY LLM request, so every word costs tokens.**

Design principles:
- Maximum 500 words (target ~400)
- No fluff, no redundant instructions
- Structured for fast LLM parsing
- Specific enough to be useful, generic enough to not need constant editing

```markdown
# Soul

You are Claw, Daniel's personal AI assistant.

## Identity
- Efficient, direct, low-fluff. Match Daniel's communication style.
- Default language: English. Switch to Spanish if Daniel writes in Spanish.
- Never apologize unnecessarily. Never pad responses.

## Core behaviors
- When given a task: confirm understanding in 1 sentence, then execute.
- When asked a question: answer directly, cite sources if from web.
- When uncertain: say so plainly, suggest how to resolve.
- Proactive ≠ noisy. Only alert for genuinely useful things.

## Daniel's context
- Senior Associate at Dialectica (TMT consulting, Bogotá)
- Pursuing MS in Artificial Intelligence at Universidad de Los Andes
- Interests: AI/ML, aviation (commercial pilot licenses COL+US), outdoor/camping
- Actively job-searching in AI-related roles
- Timezone: America/Bogota (COT, UTC-5)

## Task priorities
1. Work tasks (Dialectica + job search) — highest priority
2. Academic tasks (ML coursework, thesis prep)
3. Personal productivity (calendar, reminders, research)
4. Learning/exploration (lowest, do when idle)

## Rules
- Never expose API keys, tokens, or credentials in chat
- Never run destructive commands (rm -rf, DROP TABLE, etc.) without explicit confirmation
- Never send messages to contacts on Daniel's behalf without approval
- Keep file operations within the workspace directory
- If a task will cost >$0.50 in estimated tokens, warn before proceeding

## Output format defaults
- Use markdown for structured content
- Keep responses under 300 words unless the task requires more
- For research: bullet summaries with sources, not essays
- For code: include comments, no boilerplate explanations
```

**[NEEDS INPUT]:** Daniel — review this SOUL.md. Adjust:
- Any additional rules or constraints?
- Preferred communication style tweaks?
- Any specific tools/apps you use daily that should be mentioned?
- Do you want Spanish as default instead of English?

### 2.2 USER.md

```markdown
# User Profile

## Professional
- Name: Daniel
- Role: Senior Associate, Dialectica (Technology, Media & Telecommunications)
- Location: Bogotá, Colombia
- Previous: Forensics Investigations at Kroll, Operations at Normacol S.A.S., Research at UniAndes
- Education: Pursuing MS in Artificial Intelligence, Universidad de Los Andes

## Job search
- Actively seeking AI-related roles
- Target: positions combining consulting background + AI expertise
- Recent applications: AI Enablement & Project Specialist (Superside), AI podcast/community roles
- Preferred: remote or Bogotá-based, English or Spanish

## Technical
- Languages: Python (primary), familiar with JS/Node
- ML coursework: polynomial regression, bias-variance tradeoff, validation, classification, logistic regression
- Tools: familiar with Claude ecosystem, DataCamp, various AI platforms
- Aviation: commercial pilot licenses (Colombian CAA + US FAA)

## Preferences
- Direct communication, no fluff
- Analytical/evidence-based decision making
- Prefers structured deliverables (tables, checklists, comparisons)
- Timezone: America/Bogota (UTC-5)
```

### 2.3 AGENTS.md

This configures model routing. The key optimization: Haiku for cheap tasks, Sonnet for complex ones.

```markdown
# Agents Configuration

## Default Agent
- Model: Claude Haiku 4.5 (anthropic/claude-haiku-4-5)
- Use for: general chat, Q&A, simple file operations, formatting, reminders, heartbeat
- Max tokens per response: 2048

## Escalation Rules
- Switch to Sonnet 4.5 for: code generation, skill creation, multi-step tool use, technical analysis
- Switch to Opus 4.6 for: architecture decisions, complex research synthesis (manual trigger only via /model opus)
- Always confirm before switching to Opus

## Token Guardrails
- Compaction mode: safeguard
- Max concurrent tasks: 4
- Max concurrent subagents: 4
- Heartbeat interval: 55 minutes (aligns with Anthropic 60-min cache TTL)

## Fallback chain
1. anthropic/claude-haiku-4-5 (primary)
2. anthropic/claude-sonnet-4-5 (escalation)
3. anthropic/claude-opus-4-6 (manual only)
```

### 2.4 openclaw-config.json

This is the actual `openclaw.json` template. Secrets are placeholders.

```json
{
  "gateway": {
    "port": 18789,
    "bind": "loopback",
    "auth": {
      "token": "REPLACE_WITH_GATEWAY_TOKEN"
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "anthropic/claude-haiku-4-5",
        "fallbacks": [
          "anthropic/claude-sonnet-4-5"
        ]
      },
      "workspace": "/home/node/.openclaw/workspace",
      "compaction": {
        "mode": "safeguard"
      },
      "maxConcurrent": 4,
      "subagents": {
        "maxConcurrent": 4
      }
    }
  },
  "heartbeat": {
    "interval": "55m"
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "REPLACE_WITH_TELEGRAM_BOT_TOKEN",
      "dmPolicy": "pairing"
    }
  },
  "providers": {
    "anthropic": {
      "apiKey": "REPLACE_WITH_ANTHROPIC_API_KEY"
    }
  }
}
```

### 2.5 HEARTBEAT.md

```markdown
# Heartbeat Configuration

## Schedule
- Interval: every 55 minutes (keeps Anthropic prompt cache warm at 60-min TTL)
- Active hours: 07:00 - 23:00 COT (UTC-5)
- Silent hours: 23:00 - 07:00 (no proactive messages)

## Heartbeat tasks (in order)
1. Check for unread Telegram messages that need follow-up
2. Review pending reminders/tasks due within 2 hours
3. If morning (07:00-08:00): prepare daily briefing (calendar, weather, top news in AI/tech)
4. If evening (20:00-21:00): summarize what was accomplished today

## Rules
- Heartbeat should complete in <30 seconds
- If nothing actionable, do NOT send a message (stay silent)
- Never wake Daniel during silent hours unless explicitly overridden
```

### 2.6 MEMORY.md

```markdown
# Memory

## Initial seeds
- Daniel is based in Bogotá, Colombia (UTC-5)
- Work at Dialectica focuses on TMT consulting
- Currently studying ML: recently covered polynomial regression, bias-variance tradeoff, logistic regression
- Job searching in AI space — track any leads mentioned in conversation
- Prefers evidence-based, structured communication
```

### 2.7 Custom Skills

#### skills/daily-briefing/SKILL.md
```markdown
---
name: daily-briefing
description: Generate a morning briefing with calendar, weather, and AI/tech news
triggers:
  - "morning briefing"
  - "daily summary"
  - "start my day"
schedule: "0 7 * * *"
---

# Daily Briefing Skill

## What it does
Generates a concise morning briefing delivered via Telegram.

## Sections (in order)
1. **Today's schedule** — Pull from calendar if connected, otherwise ask Daniel
2. **Weather** — Bogotá forecast (high/low, rain probability)
3. **AI/Tech headlines** — Top 3-5 items from the past 24h relevant to AI, ML, TMT
4. **Pending tasks** — Any open reminders or follow-ups from yesterday
5. **Job search updates** — If any saved searches or applications have updates

## Format
- Total length: max 200 words
- Bullet points, no prose
- Include links for news items

## Model
- Use Haiku for this task (it's a routine aggregation, not complex reasoning)
```

#### skills/research-assistant/SKILL.md
```markdown
---
name: research-assistant
description: Deep research on a topic with structured output
triggers:
  - "research"
  - "deep dive"
  - "analyze"
---

# Research Assistant Skill

## What it does
When Daniel asks for research on a topic, produce a structured analysis.

## Process
1. Clarify scope in 1 sentence (confirm with Daniel if ambiguous)
2. Web search for recent, high-quality sources (prioritize: papers, official docs, reputable outlets)
3. Synthesize into structured output

## Output format
- **Summary** (3-5 sentences)
- **Key findings** (numbered list, max 7 items)
- **Sources** (linked, with publication date)
- **Implications for Daniel** (1-2 sentences connecting to his work/studies)
- **Confidence level** (high/medium/low with explanation)

## Model
- Use Sonnet for this task (requires synthesis and judgment)
- If topic is highly specialized or ambiguous, suggest escalating to Opus
```

#### skills/task-tracker/SKILL.md
```markdown
---
name: task-tracker
description: Track tasks, deadlines, and follow-ups
triggers:
  - "add task"
  - "remind me"
  - "what's pending"
  - "todo"
---

# Task Tracker Skill

## What it does
Maintains a simple task list in a local markdown file.

## Storage
- File: workspace/tasks.md
- Format: markdown checklist with dates and priorities

## Commands
- "add task [description] by [date]" → adds to list
- "what's pending" → shows uncompleted tasks sorted by due date
- "done [task description]" → marks as completed with timestamp
- "priorities" → shows tasks sorted by priority (high/medium/low)

## Rules
- Auto-assign priority based on context (work > academic > personal)
- Warn if a task is overdue
- Include task count in daily briefing

## Model
- Use Haiku (simple file operations)
```

---

## PHASE 3: Sentinel (Sysadmin Bot)

This is a standalone Python application. Build it with full test coverage using mocked API calls.

### 3.1 Requirements

```
# sentinel/requirements.txt
anthropic>=0.42.0
python-telegram-bot>=21.0
python-dotenv>=1.0.0
psutil>=6.0.0
paramiko>=3.5.0
docker>=7.0.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
pytest-mock>=3.14.0
```

### 3.2 config.py

```python
"""Sentinel configuration management."""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SentinelConfig:
    """Configuration for the Sentinel sysadmin bot."""

    # Telegram
    telegram_token: str = field(default_factory=lambda: os.getenv("SENTINEL_TELEGRAM_TOKEN", ""))
    allowed_user_ids: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("SENTINEL_ALLOWED_USERS", "").split(",") if x.strip()
    ])

    # Anthropic
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("SENTINEL_MODEL", "claude-haiku-4-5"))
    max_tokens: int = 1024

    # System
    openclaw_container_name: str = "openclaw-openclaw-gateway-1"
    log_file: str = "/var/log/sentinel/sentinel.log"
    workspace: str = os.path.expanduser("~/.sentinel")

    def validate(self) -> list[str]:
        """Return list of configuration errors."""
        errors = []
        if not self.telegram_token:
            errors.append("SENTINEL_TELEGRAM_TOKEN is not set")
        if not self.allowed_user_ids:
            errors.append("SENTINEL_ALLOWED_USERS is not set (comma-separated Telegram user IDs)")
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is not set")
        return errors
```

### 3.3 tools.py — Tool definitions for Anthropic SDK

```python
"""Tool definitions and execution for Sentinel sysadmin bot.

Each tool is a function that can be called by Claude via tool_use.
Tools are restricted to safe operations. Destructive commands require confirmation.
"""
import subprocess
import shlex
import psutil
import docker
from typing import Any


# --- TOOL DEFINITIONS (sent to Anthropic API) ---

TOOLS = [
    {
        "name": "system_stats",
        "description": "Get current CPU, memory, disk usage, and uptime of the VPS.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "docker_status",
        "description": "List all Docker containers with their status, uptime, and resource usage.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "docker_restart",
        "description": "Restart a Docker container by name. Use for recovering crashed services.",
        "input_schema": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "description": "Name of the container to restart"
                }
            },
            "required": ["container_name"]
        }
    },
    {
        "name": "docker_logs",
        "description": "Get recent logs from a Docker container.",
        "input_schema": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "description": "Name of the container"
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to retrieve (default 50, max 200)"
                }
            },
            "required": ["container_name"]
        }
    },
    {
        "name": "run_command",
        "description": "Execute a shell command on the VPS. RESTRICTED: only whitelisted commands allowed (systemctl, journalctl, df, free, top, ufw, ss, ping, dig, curl for health checks). No rm, no sudo su, no package management.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "check_security",
        "description": "Run a basic security audit: check open ports, failed SSH attempts, UFW status, running services, disk encryption status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "check_openclaw_health",
        "description": "Verify OpenClaw gateway is running, check its logs for errors, and report uptime.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "backup_openclaw",
        "description": "Create a compressed backup of OpenClaw's config and workspace directories.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# --- COMMAND WHITELIST ---

ALLOWED_COMMAND_PREFIXES = [
    "systemctl status", "systemctl is-active",
    "journalctl", "df", "free", "uptime", "top -bn1",
    "ufw status", "ss -tlnp", "ping -c", "dig",
    "curl -s http://127.0.0.1", "cat /var/log/auth.log",
    "last -n", "who", "w", "ps aux",
    "docker stats --no-stream", "docker ps",
    "tail -n", "head -n", "wc -l",
    "date", "timedatectl", "hostnamectl",
]

BLOCKED_PATTERNS = [
    "rm ", "rm\t", "rmdir", "mkfs", "dd ", "format",
    "sudo su", "sudo -i", "sudo bash",
    "apt ", "apt-get", "dpkg", "snap ",
    "> /dev/", "chmod 777", "wget ", # no arbitrary downloads
    "curl -o", "curl -O", # no file downloads via curl
    "python ", "node ", "bash -c", "sh -c", # no arbitrary script execution
    "export ", "unset ", "env ", # no env manipulation
    "passwd", "useradd", "userdel", "usermod",
    "reboot", "shutdown", "halt", "init ",
]


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if a command is in the whitelist and not in the blocklist."""
    command_stripped = command.strip()

    # Check blocklist first
    for pattern in BLOCKED_PATTERNS:
        if pattern in command_stripped:
            return False, f"Blocked pattern detected: '{pattern}'"

    # Check whitelist
    for prefix in ALLOWED_COMMAND_PREFIXES:
        if command_stripped.startswith(prefix):
            return True, "OK"

    return False, f"Command not in whitelist. Allowed prefixes: {', '.join(ALLOWED_COMMAND_PREFIXES[:5])}..."


# --- TOOL EXECUTORS ---

def execute_system_stats() -> dict[str, Any]:
    """Get system resource usage."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = psutil.boot_time()

    import datetime
    uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(boot_time)

    return {
        "cpu_percent": cpu_percent,
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "memory_used_gb": round(memory.used / (1024**3), 2),
        "memory_percent": memory.percent,
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_percent": disk.percent,
        "uptime": str(uptime).split(".")[0]
    }


def execute_docker_status() -> list[dict[str, str]]:
    """List all Docker containers."""
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        return [
            {
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else "unknown",
                "created": str(c.attrs["Created"])[:19],
            }
            for c in containers
        ]
    except docker.errors.DockerException as e:
        return [{"error": str(e)}]


def execute_docker_restart(container_name: str) -> dict[str, str]:
    """Restart a Docker container."""
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=30)
        return {"status": "restarted", "container": container_name}
    except docker.errors.NotFound:
        return {"error": f"Container '{container_name}' not found"}
    except docker.errors.DockerException as e:
        return {"error": str(e)}


def execute_docker_logs(container_name: str, lines: int = 50) -> str:
    """Get recent logs from a container."""
    lines = min(lines, 200)  # Cap at 200
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        return container.logs(tail=lines).decode("utf-8", errors="replace")
    except docker.errors.NotFound:
        return f"Container '{container_name}' not found"
    except docker.errors.DockerException as e:
        return str(e)


def execute_run_command(command: str) -> dict[str, Any]:
    """Execute a whitelisted shell command."""
    allowed, reason = is_command_allowed(command)
    if not allowed:
        return {"error": f"Command blocked: {reason}"}

    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "stdout": result.stdout[:4000],  # Truncate to save tokens
            "stderr": result.stderr[:1000] if result.stderr else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out (30s limit)"}
    except Exception as e:
        return {"error": str(e)}


def execute_check_security() -> dict[str, Any]:
    """Run basic security audit."""
    checks = {}

    # UFW status
    try:
        ufw = subprocess.run(["ufw", "status", "verbose"], capture_output=True, text=True, timeout=10)
        checks["ufw"] = ufw.stdout[:500]
    except Exception:
        checks["ufw"] = "Could not check UFW"

    # Failed SSH attempts (last 20)
    try:
        auth = subprocess.run(
            ["grep", "Failed password", "/var/log/auth.log"],
            capture_output=True, text=True, timeout=10
        )
        lines = auth.stdout.strip().split("\n")
        checks["failed_ssh_attempts"] = len([l for l in lines if l.strip()])
        checks["last_failed_ssh"] = lines[-1][:200] if lines and lines[0] else "None"
    except Exception:
        checks["failed_ssh_attempts"] = "Could not check"

    # Open ports
    try:
        ports = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=10)
        checks["listening_ports"] = ports.stdout[:1000]
    except Exception:
        checks["listening_ports"] = "Could not check"

    # Running services
    try:
        services = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        checks["running_services_count"] = services.stdout.count("running")
    except Exception:
        checks["running_services_count"] = "Could not check"

    return checks


def execute_check_openclaw_health() -> dict[str, Any]:
    """Check OpenClaw gateway health."""
    health = {}

    try:
        client = docker.from_env()
        container = client.containers.get("openclaw-openclaw-gateway-1")
        health["status"] = container.status
        health["uptime"] = str(container.attrs.get("State", {}).get("StartedAt", "unknown"))[:19]

        # Check recent logs for errors
        logs = container.logs(tail=20).decode("utf-8", errors="replace")
        error_lines = [l for l in logs.split("\n") if "error" in l.lower() or "fatal" in l.lower()]
        health["recent_errors"] = error_lines[-5:] if error_lines else []

        # Check gateway HTTP response
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:18789/"],
                capture_output=True, text=True, timeout=5
            )
            health["http_status"] = result.stdout.strip()
        except Exception:
            health["http_status"] = "unreachable"

    except docker.errors.NotFound:
        health["status"] = "container not found"
    except docker.errors.DockerException as e:
        health["status"] = f"docker error: {str(e)}"

    return health


def execute_backup_openclaw() -> dict[str, str]:
    """Backup OpenClaw configuration and workspace."""
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"/root/backups/openclaw-{timestamp}.tar.gz"

    try:
        subprocess.run(["mkdir", "-p", "/root/backups"], check=True)
        result = subprocess.run(
            ["tar", "czf", backup_path, "/root/.openclaw/"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            # Get file size
            import os
            size = os.path.getsize(backup_path)
            return {"status": "success", "path": backup_path, "size_mb": round(size / (1024*1024), 2)}
        else:
            return {"status": "failed", "error": result.stderr[:500]}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# --- TOOL DISPATCHER ---

def execute_tool(tool_name: str, tool_input: dict) -> Any:
    """Dispatch tool execution by name."""
    executors = {
        "system_stats": lambda _: execute_system_stats(),
        "docker_status": lambda _: execute_docker_status(),
        "docker_restart": lambda inp: execute_docker_restart(inp["container_name"]),
        "docker_logs": lambda inp: execute_docker_logs(inp["container_name"], inp.get("lines", 50)),
        "run_command": lambda inp: execute_run_command(inp["command"]),
        "check_security": lambda _: execute_check_security(),
        "check_openclaw_health": lambda _: execute_check_openclaw_health(),
        "backup_openclaw": lambda _: execute_backup_openclaw(),
    }

    executor = executors.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}

    return executor(tool_input)
```

### 3.4 sentinel.py — Main bot with Anthropic SDK

```python
"""Sentinel: Sysadmin bot for OpenClaw VPS management.

Uses Anthropic SDK with tool_use for infrastructure management.
Accessed via Telegram. Restricted to authorized users only.
"""
import json
import logging
import asyncio
from anthropic import Anthropic

from config import SentinelConfig
from tools import TOOLS, execute_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("sentinel")

SYSTEM_PROMPT = """You are Sentinel, a sysadmin bot managing a Hetzner CPX32 VPS.

Your responsibilities:
- Monitor system health (CPU, RAM, disk, network)
- Manage Docker containers (especially the OpenClaw gateway)
- Run security audits and report findings
- Create backups of OpenClaw configuration
- Diagnose and fix common issues
- Report status clearly and concisely

Rules:
- Only use the tools provided. Do not suggest manual SSH commands.
- If something looks dangerous or unusual, alert the user and wait for confirmation.
- Keep responses concise — this is Telegram, not an essay.
- If a restart or destructive action is requested, confirm before executing.
- Never expose secrets, tokens, or API keys in responses.
- Use bullet points for status reports.

The VPS runs:
- Ubuntu 24.04 LTS
- Docker with OpenClaw gateway container
- UFW firewall (SSH only inbound)
- fail2ban for SSH protection
- This bot (Sentinel) as a systemd service
"""


class SentinelAgent:
    """Anthropic-powered sysadmin agent with tool use."""

    def __init__(self, config: SentinelConfig):
        self.config = config
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.conversations: dict[int, list] = {}  # user_id -> message history

    def process_message(self, user_id: int, user_message: str) -> str:
        """Process a user message through Claude with tool use.

        Implements the agentic loop: send message → get tool_use → execute → feed back → repeat.
        """
        # Initialize or retrieve conversation history (keep last 10 exchanges)
        if user_id not in self.conversations:
            self.conversations[user_id] = []

        history = self.conversations[user_id]
        history.append({"role": "user", "content": user_message})

        # Trim history to last 10 exchanges (20 messages) to control token usage
        if len(history) > 20:
            history = history[-20:]
            self.conversations[user_id] = history

        # Agentic loop
        max_iterations = 5  # Prevent infinite tool loops
        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=history,
            )

            # Check if response contains tool use
            if response.stop_reason == "tool_use":
                # Process all tool calls in the response
                assistant_content = response.content
                history.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        logger.info(f"Executing tool: {block.name}({json.dumps(block.input)[:200]})")
                        result = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str)[:4000],  # Truncate
                        })

                history.append({"role": "user", "content": tool_results})
                continue  # Loop back for Claude to process results

            else:
                # Final text response
                text_response = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_response += block.text

                history.append({"role": "assistant", "content": response.content})
                self.conversations[user_id] = history
                return text_response

        return "⚠️ Reached maximum tool iterations. Something may be stuck. Please try again."
```

### 3.5 telegram_handler.py

```python
"""Telegram bot interface for Sentinel."""
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import SentinelConfig
from sentinel import SentinelAgent

logger = logging.getLogger("sentinel.telegram")


class SentinelTelegramBot:
    """Telegram interface for the Sentinel sysadmin bot."""

    def __init__(self, config: SentinelConfig, agent: SentinelAgent):
        self.config = config
        self.agent = agent

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is in the allowed list."""
        return user_id in self.config.allowed_user_ids

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized. This bot is restricted.")
            return

        await update.message.reply_text(
            "🛡️ *Sentinel Online*\n\n"
            "I manage your VPS infrastructure. Commands:\n"
            "• `/status` — System stats\n"
            "• `/openclaw` — OpenClaw health\n"
            "• `/security` — Security audit\n"
            "• `/backup` — Backup OpenClaw\n"
            "• Or just describe what you need in plain text.\n\n"
            "All requests go through Claude with tool verification.",
            parse_mode="Markdown"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Quick system status."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Give me a quick system status: CPU, RAM, disk, and Docker containers. Be concise."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def openclaw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check OpenClaw health."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Check OpenClaw gateway health: is it running, any recent errors, HTTP status."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run security audit."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Run a security audit: UFW status, failed SSH attempts, open ports, running services."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger OpenClaw backup."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Create a backup of OpenClaw's config and workspace. Report the file path and size."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle free-text messages."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized.")
            return

        user_message = update.message.text
        logger.info(f"Message from {update.effective_user.id}: {user_message[:100]}")

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        try:
            response = self.agent.process_message(update.effective_user.id, user_message)
            # Telegram has a 4096 char limit per message
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000], parse_mode="Markdown")
            else:
                await update.message.reply_text(response, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await update.message.reply_text(f"⚠️ Error: {str(e)[:200]}")

    def run(self) -> None:
        """Start the Telegram bot."""
        app = Application.builder().token(self.config.telegram_token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("openclaw", self.openclaw_command))
        app.add_handler(CommandHandler("security", self.security_command))
        app.add_handler(CommandHandler("backup", self.backup_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Sentinel Telegram bot starting...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Entry point."""
    config = SentinelConfig()
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error(f"Config error: {e}")
        raise SystemExit(1)

    agent = SentinelAgent(config)
    bot = SentinelTelegramBot(config, agent)
    bot.run()


if __name__ == "__main__":
    main()
```

### 3.6 Tests (mocked — no API calls)

Create `sentinel/tests/conftest.py`:

```python
"""Shared test fixtures."""
import pytest
from unittest.mock import MagicMock, patch
from config import SentinelConfig


@pytest.fixture
def mock_config():
    """Config with test values."""
    return SentinelConfig(
        telegram_token="test-token-123",
        allowed_user_ids=[12345],
        anthropic_api_key="test-api-key",
        model="claude-haiku-4-5",
    )


@pytest.fixture
def mock_anthropic_client():
    """Mocked Anthropic client that returns a text response."""
    with patch("sentinel.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Default: return a simple text response (no tool use)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "System is healthy. CPU: 12%, RAM: 45%, Disk: 23%."
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        yield mock_client
```

Create `sentinel/tests/test_tools.py`:

```python
"""Tests for tool definitions and execution."""
import pytest
from unittest.mock import patch, MagicMock
from tools import is_command_allowed, execute_tool, TOOLS


class TestCommandWhitelist:
    """Test the command whitelist/blocklist logic."""

    def test_allowed_commands(self):
        assert is_command_allowed("df -h")[0] is True
        assert is_command_allowed("free -m")[0] is True
        assert is_command_allowed("uptime")[0] is True
        assert is_command_allowed("ufw status")[0] is True
        assert is_command_allowed("docker ps")[0] is True

    def test_blocked_commands(self):
        assert is_command_allowed("rm -rf /")[0] is False
        assert is_command_allowed("sudo su")[0] is False
        assert is_command_allowed("apt install something")[0] is False
        assert is_command_allowed("wget http://malicious.com")[0] is False
        assert is_command_allowed("python malicious.py")[0] is False
        assert is_command_allowed("reboot")[0] is False
        assert is_command_allowed("chmod 777 /etc/passwd")[0] is False

    def test_unknown_commands_blocked(self):
        assert is_command_allowed("some-random-binary")[0] is False
        assert is_command_allowed("nc -l 4444")[0] is False

    def test_whitelist_is_prefix_based(self):
        assert is_command_allowed("systemctl status openclaw")[0] is True
        assert is_command_allowed("systemctl restart openclaw")[0] is False  # restart not whitelisted


class TestToolDefinitions:
    """Verify tool schema integrity."""

    def test_all_tools_have_required_fields(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_tool_count(self):
        assert len(TOOLS) == 8


class TestSystemStats:
    """Test system stats tool."""

    @patch("tools.psutil")
    def test_system_stats_returns_expected_keys(self, mock_psutil):
        mock_psutil.cpu_percent.return_value = 15.0
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=8 * 1024**3, used=3 * 1024**3, percent=37.5
        )
        mock_psutil.disk_usage.return_value = MagicMock(
            total=160 * 1024**3, used=20 * 1024**3, percent=12.5
        )
        mock_psutil.boot_time.return_value = 1700000000.0

        result = execute_tool("system_stats", {})
        assert "cpu_percent" in result
        assert "memory_percent" in result
        assert "disk_percent" in result
        assert "uptime" in result


class TestDockerTools:
    """Test Docker management tools."""

    @patch("tools.docker.from_env")
    def test_docker_status(self, mock_docker):
        mock_container = MagicMock()
        mock_container.name = "openclaw-gateway"
        mock_container.status = "running"
        mock_container.image.tags = ["openclaw:latest"]
        mock_container.attrs = {"Created": "2026-02-18T10:00:00"}
        mock_docker.return_value.containers.list.return_value = [mock_container]

        result = execute_tool("docker_status", {})
        assert len(result) == 1
        assert result[0]["name"] == "openclaw-gateway"
        assert result[0]["status"] == "running"

    @patch("tools.docker.from_env")
    def test_docker_restart(self, mock_docker):
        mock_container = MagicMock()
        mock_docker.return_value.containers.get.return_value = mock_container

        result = execute_tool("docker_restart", {"container_name": "openclaw-gateway"})
        assert result["status"] == "restarted"
        mock_container.restart.assert_called_once_with(timeout=30)
```

### 3.7 sentinel.service (systemd unit file)

```ini
[Unit]
Description=Sentinel Sysadmin Bot
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sentinel
ExecStart=/opt/sentinel/venv/bin/python sentinel.py
Restart=always
RestartSec=10
Environment=PATH=/opt/sentinel/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
```

---

## PHASE 4: Infrastructure Scripts

### 4.1 infrastructure/env.template

```bash
# === OpenClaw ===
OPENCLAW_IMAGE=openclaw:hetzner
OPENCLAW_GATEWAY_TOKEN=       # Generate: openssl rand -hex 32
OPENCLAW_GATEWAY_BIND=lan
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_CONFIG_DIR=/root/.openclaw
OPENCLAW_WORKSPACE_DIR=/root/.openclaw/workspace
GOG_KEYRING_PASSWORD=         # Generate: openssl rand -hex 32
XDG_CONFIG_HOME=/home/node/.openclaw

# === Sentinel ===
SENTINEL_TELEGRAM_TOKEN=      # From @BotFather (sysadmin bot)
SENTINEL_ALLOWED_USERS=       # Your Telegram user ID (comma-separated)
SENTINEL_MODEL=claude-haiku-4-5

# === Shared ===
ANTHROPIC_API_KEY=            # From console.anthropic.com

# === OpenClaw Telegram ===
OPENCLAW_TELEGRAM_TOKEN=      # From @BotFather (assistant bot)
```

### 4.2 infrastructure/secure.sh

```bash
#!/usr/bin/env bash
# Security hardening script for Hetzner CPX32
# Run as root on first VPS setup
set -euo pipefail

echo "=== [1/6] System update ==="
apt-get update && apt-get upgrade -y

echo "=== [2/6] Install essentials ==="
apt-get install -y ufw fail2ban curl git ca-certificates unattended-upgrades

echo "=== [3/6] Configure UFW firewall ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
# Do NOT open 18789 — access via SSH tunnel only
echo "y" | ufw enable
ufw status verbose

echo "=== [4/6] Configure fail2ban ==="
cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

echo "=== [5/6] SSH hardening ==="
# Disable password auth (SSH key only)
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart sshd

echo "=== [6/6] Enable automatic security updates ==="
dpkg-reconfigure -plow unattended-upgrades

echo ""
echo "✅ Security hardening complete."
echo "   - UFW: active (SSH only)"
echo "   - fail2ban: active (3 attempts, 1h ban)"
echo "   - SSH: key-only auth"
echo "   - Auto-updates: enabled"
```

### 4.3 infrastructure/deploy.sh

```bash
#!/usr/bin/env bash
# Full deployment script — run on the VPS after scp'ing the project
set -euo pipefail

PROJECT_DIR="/root/openclaw-project"
OPENCLAW_DIR="/root/openclaw"
SENTINEL_DIR="/opt/sentinel"

echo "=== [1/8] Install Docker ==="
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
docker --version
docker compose version

echo "=== [2/8] Clone OpenClaw ==="
if [ ! -d "$OPENCLAW_DIR" ]; then
    git clone https://github.com/openclaw/openclaw.git "$OPENCLAW_DIR"
fi
cd "$OPENCLAW_DIR"
git pull

echo "=== [3/8] Create persistent directories ==="
mkdir -p /root/.openclaw/workspace /root/.openclaw/skills /root/backups
chown -R 1000:1000 /root/.openclaw

echo "=== [4/8] Copy OpenClaw config files ==="
cp "$PROJECT_DIR/openclaw/config/SOUL.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/USER.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/AGENTS.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/HEARTBEAT.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/MEMORY.md" /root/.openclaw/
cp -r "$PROJECT_DIR/openclaw/skills/"* /root/.openclaw/skills/ 2>/dev/null || true

echo "=== [5/8] Copy infrastructure files ==="
cp "$PROJECT_DIR/infrastructure/Dockerfile" "$OPENCLAW_DIR/"
cp "$PROJECT_DIR/infrastructure/docker-compose.yml" "$OPENCLAW_DIR/"

echo "=== [6/8] Setup Sentinel ==="
mkdir -p "$SENTINEL_DIR"
cp "$PROJECT_DIR/sentinel/"*.py "$SENTINEL_DIR/"
cp "$PROJECT_DIR/sentinel/requirements.txt" "$SENTINEL_DIR/"
cp "$PROJECT_DIR/sentinel/sentinel.service" /etc/systemd/system/

# Create Python venv for Sentinel
python3 -m venv "$SENTINEL_DIR/venv"
"$SENTINEL_DIR/venv/bin/pip" install -r "$SENTINEL_DIR/requirements.txt"

echo "=== [7/8] Build OpenClaw Docker image ==="
cd "$OPENCLAW_DIR"
# Copy .env (must be created manually with secrets)
if [ ! -f .env ]; then
    cp "$PROJECT_DIR/infrastructure/env.template" .env
    echo ""
    echo "⚠️  IMPORTANT: Edit /root/openclaw/.env and fill in all secrets before starting!"
    echo "   Run: nano /root/openclaw/.env"
    echo ""
fi
docker compose build

echo "=== [8/8] Enable Sentinel service ==="
systemctl daemon-reload
systemctl enable sentinel

echo ""
echo "✅ Deployment staged. NOT yet running."
echo ""
echo "Next steps:"
echo "  1. Edit secrets:    nano /root/openclaw/.env"
echo "  2. Start OpenClaw:  cd /root/openclaw && docker compose up -d"
echo "  3. Start Sentinel:  systemctl start sentinel"
echo "  4. SSH tunnel:      ssh -N -L 18789:127.0.0.1:18789 root@YOUR_VPS_IP"
echo "  5. Open browser:    http://127.0.0.1:18789/"
```

### 4.4 infrastructure/backup.sh

```bash
#!/usr/bin/env bash
# Automated backup of OpenClaw state
set -euo pipefail

BACKUP_DIR="/root/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/openclaw-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

tar czf "$BACKUP_FILE" \
    /root/.openclaw/ \
    /opt/sentinel/*.py \
    /opt/sentinel/requirements.txt \
    /root/openclaw/.env \
    2>/dev/null

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/openclaw-*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Backup created: $BACKUP_FILE ($SIZE)"
```

### 4.5 infrastructure/ssh-config-snippet

```
# Add this to ~/.ssh/config on your Mac

Host openclaw
    HostName REPLACE_WITH_VPS_IP
    User root
    IdentityFile ~/.ssh/id_ed25519
    LocalForward 18789 127.0.0.1:18789
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

---

## PHASE 5: Documentation

### 5.1 docs/DEPLOYMENT.md

Create a step-by-step deployment guide covering:
1. Provision Hetzner CPX32 (Ubuntu 24.04, add SSH key, Falkenstein or Nuremberg)
2. First SSH connection from Mac
3. Run secure.sh
4. SCP the project: `scp -r ~/openclaw-project root@VPS_IP:/root/`
5. Run deploy.sh
6. Fill in .env with real secrets
7. Start services
8. Verify via SSH tunnel

### 5.2 docs/PHASE3-CHECKLIST.md

```markdown
# Phase 3: Go-Live Checklist

## Before starting (on your Mac)
- [ ] Hetzner CPX32 provisioned with Ubuntu 24.04
- [ ] SSH key added to VPS
- [ ] Can SSH into VPS: `ssh root@YOUR_VPS_IP`
- [ ] Anthropic API key created with $5 spending limit set
- [ ] Two Telegram bots created via @BotFather:
  - [ ] Bot 1: OpenClaw assistant (name: your_claw_bot)
  - [ ] Bot 2: Sentinel sysadmin (name: your_sentinel_bot)
- [ ] Your Telegram user ID noted (get from @userinfobot)

## Deployment (on VPS)
- [ ] secure.sh ran successfully
- [ ] deploy.sh ran successfully
- [ ] .env filled with all real values
- [ ] Docker image built without errors

## Go live
- [ ] `docker compose up -d` — OpenClaw gateway starts
- [ ] `docker compose logs -f` — shows "listening on ws://0.0.0.0:18789"
- [ ] SSH tunnel active: `ssh openclaw`
- [ ] Browser: http://127.0.0.1:18789/ loads, token accepted
- [ ] Telegram: /start on OpenClaw bot → pairing works
- [ ] Send test message: "What time is it?" → bot responds
- [ ] `systemctl start sentinel` — Sentinel starts
- [ ] Telegram: /status on Sentinel bot → system stats returned

## Verification (budget: ~$2-5 API cost)
- [ ] OpenClaw: "Create a task: test task tracker" → skill works
- [ ] OpenClaw: "What's the weather in Bogotá?" → web search works
- [ ] Sentinel: /security → audit completes
- [ ] Sentinel: /openclaw → health check passes
- [ ] Sentinel: /backup → backup created

## Post-verification
- [ ] Raise Anthropic spending limit to $25/month
- [ ] Set up backup cron: `crontab -e` → `0 3 * * * /root/openclaw-project/infrastructure/backup.sh`
- [ ] Monitor first 24h of API usage on console.anthropic.com
```

### 5.3 docs/COST-MANAGEMENT.md

```markdown
# Cost Management Guide

## Monthly budget breakdown
| Component | Cost |
|---|---|
| Hetzner CPX32 | €10.99 (~$13) |
| LLM API (target) | $10-25 |
| **Total target** | **$23-38/month** |

## Anthropic spending limits
1. Go to console.anthropic.com → Settings → Billing
2. Set monthly limit: $25 (Phase 3 testing), then adjust
3. Set alert at $20

## Token optimization checklist
- [ ] SOUL.md is under 500 words
- [ ] Heartbeat interval is 55 minutes (cache-aligned)
- [ ] Default model is Haiku 4.5 (not Sonnet)
- [ ] Compaction mode is "safeguard"
- [ ] Sentinel uses Haiku exclusively
- [ ] No proactive messages during silent hours (23:00-07:00)

## Monitoring
- Check daily: console.anthropic.com → Usage
- Check weekly: total token count and cost per day trend
- If >$1/day consistently: review which tasks are using Sonnet/Opus and whether they need to
```

---

## PHASE 6: Final Verification (Local Only)

Before deploying anything, verify locally on the Mac:

### 6.1 Run Sentinel tests
```bash
cd ~/openclaw-project/sentinel
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

All tests should pass with mocked API calls. Zero API cost.

### 6.2 Validate all config files
```bash
# Check JSON syntax
python3 -c "import json; json.load(open('openclaw/openclaw-config.json'))"

# Check markdown files exist and are non-empty
for f in openclaw/config/*.md; do
    echo "$f: $(wc -w < "$f") words"
done

# Check SOUL.md is under 500 words
WORDS=$(wc -w < openclaw/config/SOUL.md)
if [ "$WORDS" -gt 500 ]; then
    echo "⚠️ SOUL.md is $WORDS words — too long, trim to <500"
else
    echo "✅ SOUL.md: $WORDS words (good)"
fi
```

### 6.3 Dry-run Docker build (optional, if Docker Desktop is installed)
```bash
cd ~/openclaw-project/infrastructure
# This just validates the Dockerfile syntax, doesn't need the VPS
docker build --dry-run . 2>/dev/null && echo "✅ Dockerfile valid" || echo "⚠️ Dockerfile has issues"
```

---

## SUMMARY FOR CLAUDE CODE

**Execute phases 1-6 in order.** The human will provide input where marked [NEEDS INPUT]. Everything else can be built autonomously.

**Key constraints:**
- Zero API cost during build phase
- All tests must use mocked Anthropic API calls
- SOUL.md must be under 500 words
- Default LLM is Haiku 4.5, not Sonnet or Opus
- Sentinel command whitelist is strict — no destructive operations
- All secrets are placeholder values — never generate real keys

**When done, the human should have:**
1. A complete `~/openclaw-project/` directory
2. All Sentinel tests passing locally
3. All config files validated
4. A clear Phase 3 checklist for go-live
5. Total API cost at this point: $0.00
