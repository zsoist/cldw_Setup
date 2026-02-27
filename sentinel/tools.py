"""Tool definitions and execution for Sentinel sysadmin bot.

Each tool is a function that can be called by Claude via tool_use.
Tools are restricted to safe operations. Destructive commands require confirmation.
"""
import os
import json
import subprocess
import shlex
import re
import ipaddress
import unicodedata
import psutil
import docker
from typing import Any
from urllib.parse import urlsplit


# --- TOOL DEFINITIONS (sent to Anthropic API) ---

TOOLS = [
    {
        "name": "system_stats",
        "description": "Get CPU, RAM, disk, swap, uptime stats.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "docker_status",
        "description": "List Docker containers with status and resource usage.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "docker_restart",
        "description": "Restart a Docker container by name.",
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
        "description": "Run a whitelisted shell command (systemctl, journalctl, df, free, top, ufw, ss, ping, dig, curl).",
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
        "description": "Run security audit: ports, SSH, UFW, services.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "check_openclaw_health",
        "description": "Check OpenClaw gateway health and recent errors.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "backup_openclaw",
        "description": "Create compressed backup of OpenClaw config.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "cost_summary",
        "description": "Get API cost summary. Period: today/week/month/all.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period: 'today', 'week', 'month', 'all' (default: 'today')",
                    "enum": ["today", "week", "month", "all"]
                }
            },
            "required": []
        }
    }
]


def _to_google_function_declaration(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert Anthropic tool schema to Gemini function declaration format."""
    return {
        "name": tool["name"],
        "description": tool["description"],
        "parameters": tool["input_schema"],
    }


GOOGLE_FUNCTION_DECLARATIONS = [_to_google_function_declaration(tool) for tool in TOOLS]
GOOGLE_TOOLS = [{"function_declarations": GOOGLE_FUNCTION_DECLARATIONS}]


# --- COMMAND WHITELIST ---

BLOCKED_PATTERNS = [
    "rm ", "rm\t", "rmdir", "mkfs", "dd ", "format",
    "sudo su", "sudo -i", "sudo bash",
    "apt ", "apt-get", "dpkg", "snap ",
    "> /dev/", "chmod 777", "wget ",
    "curl -o",
    "python ", "node ", "bash -c", "sh -c",
    "export ", "unset ", "env ",
    "passwd", "useradd", "userdel", "usermod",
    "reboot", "shutdown", "halt", "init ",
]

UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")
FQDN_RE = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)
ALLOWED_DOCKER_CONTAINERS = {"openclaw-openclaw-gateway-1", "job-radar-api", "job-radar-db"}


def _is_bounded_int(value: str, min_value: int, max_value: int) -> bool:
    if not value.isdigit():
        return False
    number = int(value)
    return min_value <= number <= max_value


def _normalize_command(command: str) -> str:
    """Normalize unicode and whitespace before validation."""
    normalized = unicodedata.normalize("NFKC", command)
    return re.sub(r"[ \t]+", " ", normalized).strip()


def _is_valid_host(host: str) -> bool:
    """Allow IPv4/IPv6 literals and FQDNs only."""
    if not host or host.startswith("-"):
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(FQDN_RE.fullmatch(host))


def _validate_local_http_url(url: str) -> bool:
    """Allow http://127.0.0.1[:port][/path...] with valid port range."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "http":
        return False
    if parsed.hostname != "127.0.0.1":
        return False
    if parsed.username or parsed.password:
        return False
    if port is not None and not (1 <= port <= 65535):
        return False
    return True


def _is_allowed_container_name(container_name: str) -> bool:
    return container_name in ALLOWED_DOCKER_CONTAINERS


def _validate_systemctl(args: list[str]) -> tuple[bool, str]:
    if len(args) < 2:
        return False, "systemctl requires action and unit"
    action = args[0]
    unit = args[1]
    extra = args[2:]
    if action not in {"status", "is-active"}:
        return False, "systemctl action must be status or is-active"
    if not UNIT_NAME_RE.fullmatch(unit):
        return False, "Invalid systemctl unit name"
    if extra and extra != ["--no-pager"]:
        return False, "Only --no-pager is allowed as extra argument"
    return True, "OK"


def _validate_journalctl(args: list[str]) -> tuple[bool, str]:
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--no-pager":
            i += 1
        elif arg in {"-u", "-n", "--since", "--until"}:
            if i + 1 >= len(args):
                return False, f"{arg} requires a value"
            value = args[i + 1]
            if arg == "-u" and not UNIT_NAME_RE.fullmatch(value):
                return False, "Invalid unit name for journalctl -u"
            if arg == "-n" and not _is_bounded_int(value, 1, 1000):
                return False, "journalctl -n must be between 1 and 1000"
            i += 2
        else:
            return False, f"Unsupported journalctl argument: {arg}"
    return True, "OK"


def _validate_df(args: list[str]) -> tuple[bool, str]:
    if args in ([], ["-h"], ["/"], ["-h", "/"]):
        return True, "OK"
    return False, "Allowed: df, df -h, df /, df -h /"


def _validate_free(args: list[str]) -> tuple[bool, str]:
    if args in ([], ["-m"], ["-h"]):
        return True, "OK"
    return False, "Allowed: free, free -m, free -h"


def _validate_ufw(args: list[str]) -> tuple[bool, str]:
    if args in (["status"], ["status", "verbose"]):
        return True, "OK"
    return False, "Allowed: ufw status [verbose]"


def _validate_ping(args: list[str]) -> tuple[bool, str]:
    if len(args) != 3 or args[0] != "-c":
        return False, "Allowed: ping -c <1-5> <host>"
    if not _is_bounded_int(args[1], 1, 5):
        return False, "Ping count must be between 1 and 5"
    if not _is_valid_host(args[2]):
        return False, "Invalid ping host"
    return True, "OK"


def _validate_dig(args: list[str]) -> tuple[bool, str]:
    if len(args) != 1:
        return False, "Allowed: dig <host>"
    if not _is_valid_host(args[0]):
        return False, "Invalid host"
    return True, "OK"


def _validate_curl(args: list[str]) -> tuple[bool, str]:
    if not args:
        return False, "curl requires arguments"
    url = args[-1]
    if not _validate_local_http_url(url):
        return False, "curl is limited to local http://127.0.0.1 endpoints"
    options = args[:-1]
    if options in ([], ["-s"], ["-sf"]):
        return True, "OK"
    if options in (
        ["-s", "-o", "/dev/null", "-w", "%{http_code}"],
        ["-sf", "-o", "/dev/null", "-w", "%{http_code}"],
    ):
        return True, "OK"
    return False, "Unsupported curl options"


def _validate_last(args: list[str]) -> tuple[bool, str]:
    if len(args) == 2 and args[0] == "-n" and _is_bounded_int(args[1], 1, 100):
        return True, "OK"
    return False, "Allowed: last -n <1-100>"


def _validate_command_tokens(tokens: list[str]) -> tuple[bool, str]:
    cmd = tokens[0]
    args = tokens[1:]

    if cmd == "systemctl":
        return _validate_systemctl(args)
    if cmd == "journalctl":
        return _validate_journalctl(args)
    if cmd == "df":
        return _validate_df(args)
    if cmd == "free":
        return _validate_free(args)
    if cmd == "uptime":
        return (True, "OK") if not args else (False, "uptime takes no arguments")
    if cmd == "top":
        return (True, "OK") if args == ["-bn1"] else (False, "Allowed: top -bn1")
    if cmd == "ufw":
        return _validate_ufw(args)
    if cmd == "ss":
        return (True, "OK") if args == ["-tlnp"] else (False, "Allowed: ss -tlnp")
    if cmd == "ping":
        return _validate_ping(args)
    if cmd == "dig":
        return _validate_dig(args)
    if cmd == "curl":
        return _validate_curl(args)
    if cmd == "cat":
        return (True, "OK") if args == ["/var/log/auth.log"] else (False, "Allowed: cat /var/log/auth.log")
    if cmd == "last":
        return _validate_last(args)
    if cmd == "who":
        return (True, "OK") if not args else (False, "who takes no arguments")
    if cmd == "w":
        return (True, "OK") if not args else (False, "w takes no arguments")
    if cmd == "ps":
        return (True, "OK") if args == ["aux"] else (False, "Allowed: ps aux")
    if cmd == "docker":
        if args == ["ps", "--filter", "name=openclaw-openclaw-gateway-1"]:
            return True, "OK"
        if args == ["stats", "--no-stream", "openclaw-openclaw-gateway-1"]:
            return True, "OK"
        return False, "Allowed: docker ps --filter name=openclaw-openclaw-gateway-1 | docker stats --no-stream openclaw-openclaw-gateway-1"
    if cmd == "date":
        return (True, "OK") if not args else (False, "date takes no arguments")
    if cmd == "timedatectl":
        return (True, "OK") if not args else (False, "timedatectl takes no arguments")
    if cmd == "hostnamectl":
        return (True, "OK") if not args else (False, "hostnamectl takes no arguments")

    return False, "Command not in whitelist"


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if a command is in the whitelist and not in the blocklist."""
    command_normalized = _normalize_command(command)
    if not command_normalized:
        return False, "Empty command"
    if len(command_normalized) > 256:
        return False, "Command too long"
    if any(ord(ch) < 32 and ch not in {"\t", "\n"} for ch in command_normalized):
        return False, "Command contains control characters"
    command_lower = command_normalized.lower()

    # Check blocklist first
    for pattern in BLOCKED_PATTERNS:
        if pattern in command_lower:
            return False, f"Blocked pattern detected: '{pattern}'"

    try:
        tokens = shlex.split(command_normalized)
    except ValueError as e:
        return False, f"Invalid shell syntax: {e}"

    allowed, reason = _validate_command_tokens(tokens)
    if allowed:
        return True, "OK"

    return False, f"Command blocked: {reason}"


# --- TOOL EXECUTORS ---

def execute_system_stats() -> dict[str, Any]:
    """Get system resource usage."""
    # Keep this lightweight; 250ms sampling is enough for chat diagnostics.
    cpu_percent = psutil.cpu_percent(interval=0.25)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    swap = psutil.swap_memory()
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
        "swap_total_gb": round(swap.total / (1024**3), 2),
        "swap_used_gb": round(swap.used / (1024**3), 2),
        "uptime": str(uptime).split(".")[0]
    }


def execute_docker_status() -> dict[str, Any]:
    """List explicitly allowed Docker containers."""
    try:
        client = docker.from_env()
        containers = []
        for name in sorted(ALLOWED_DOCKER_CONTAINERS):
            try:
                c = client.containers.get(name)
                containers.append(
                    {
                        "name": c.name,
                        "status": c.status,
                        "image": c.image.tags[0] if c.image.tags else "unknown",
                        "created": str(c.attrs["Created"])[:19],
                    }
                )
            except docker.errors.NotFound:
                containers.append({"name": name, "status": "not_found"})
        return {"containers": containers}
    except docker.errors.DockerException as e:
        return {"error": str(e)}


def execute_docker_restart(container_name: str) -> dict[str, str]:
    """Restart a Docker container."""
    if not _is_allowed_container_name(container_name):
        return {"error": f"Container '{container_name}' is not in the allowlist"}
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=30)
        return {"status": "restarted", "container": container_name}
    except docker.errors.NotFound:
        return {"error": f"Container '{container_name}' not found"}
    except docker.errors.DockerException as e:
        return {"error": str(e)}


def execute_docker_logs(container_name: str, lines: int = 50) -> dict[str, Any]:
    """Get recent logs from a container."""
    lines = min(lines, 200)  # Cap at 200
    if not _is_allowed_container_name(container_name):
        return {"error": f"Container '{container_name}' is not in the allowlist"}
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        return {
            "container": container_name,
            "lines": lines,
            "logs": container.logs(tail=lines).decode("utf-8", errors="replace"),
        }
    except docker.errors.NotFound:
        return {"error": f"Container '{container_name}' not found"}
    except docker.errors.DockerException as e:
        return {"error": str(e)}


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

    # Failed SSH attempts from recent auth log window.
    # Avoid scanning the full auth.log on every invocation.
    try:
        auth_tail = subprocess.run(
            ["tail", "-n", "5000", "/var/log/auth.log"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        failed_lines = [
            line for line in auth_tail.stdout.splitlines()
            if "Failed password" in line
        ]
        checks["failed_ssh_attempts"] = len(failed_lines)
        checks["last_failed_ssh"] = failed_lines[-1][:200] if failed_lines else "None"
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
        running_units = [
            line for line in services.stdout.splitlines()
            if " loaded active running " in line
        ]
        checks["running_services_count"] = len(running_units)
    except Exception:
        checks["running_services_count"] = "Could not check"

    return checks


def execute_check_openclaw_health() -> dict[str, Any]:
    """Check OpenClaw gateway health."""
    health = {}

    try:
        client = docker.from_env()
        container = client.containers.get("openclaw-openclaw-gateway-1")
        state = container.attrs.get("State", {})
        docker_health = state.get("Health", {}).get("Status", "unknown")
        health["status"] = container.status
        health["docker_health"] = docker_health
        health["uptime"] = str(state.get("StartedAt", "unknown"))[:19]
        health["gateway_ready"] = container.status == "running" and docker_health == "healthy"

        # Check recent logs for errors
        logs = container.logs(tail=20).decode("utf-8", errors="replace")
        error_lines = [line for line in logs.split("\n") if "error" in line.lower() or "fatal" in line.lower()]
        health["recent_errors"] = error_lines[-5:] if error_lines else []

        # HTTP fallback endpoint (useful when Telegram channel is degraded)
        probe = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:18789/__openclaw__/canvas/"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        health["http_fallback_status"] = probe.stdout.strip() or "000"

    except docker.errors.NotFound:
        health["status"] = "container not found"
    except docker.errors.DockerException as e:
        health["status"] = f"docker error: {str(e)}"

    return health


def execute_backup_openclaw() -> dict[str, str]:
    """Backup OpenClaw configuration and workspace."""
    import datetime
    import os
    from pathlib import Path

    backup_dir = Path("/var/backups/openclaw")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    backup_path = backup_dir / f"openclaw-{timestamp}.tar"

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        client = docker.from_env()
        container = client.containers.get("openclaw-openclaw-gateway-1")
        stream, _ = container.get_archive("/home/node/.openclaw")
        with backup_path.open("wb") as f:
            for chunk in stream:
                f.write(chunk)

        backups = sorted(backup_dir.glob("openclaw-*.tar"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[7:]:
            old.unlink(missing_ok=True)

        size = os.path.getsize(backup_path)
        return {"status": "success", "path": str(backup_path), "size_mb": round(size / (1024 * 1024), 2)}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def execute_cost_summary(period: str = "today") -> dict[str, Any]:
    """Get API cost and token usage summary from Sentinel + OpenClaw."""
    import datetime as _dt

    result: dict[str, Any] = {"period": period, "services": {}}

    # --- Sentinel costs (from cost summary JSON) ---
    sentinel_summary_path = "/var/log/sentinel/api-cost-summary.json"
    try:
        with open(sentinel_summary_path) as f:
            summary = json.load(f)

        totals = summary.get("totals", {})
        today_key = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        week_key = _dt.datetime.now(_dt.timezone.utc).strftime("%G-W%V")
        month_key = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m")

        if period == "today":
            bucket = totals.get("daily", {}).get(today_key, {})
        elif period == "week":
            bucket = totals.get("weekly", {}).get(week_key, {})
        elif period == "month":
            bucket = totals.get("monthly", {}).get(month_key, {})
        else:
            bucket = totals.get("all_time", {})

        result["services"]["sentinel"] = {
            "usd": round(float(bucket.get("usd", 0)), 6),
            "input_tokens": int(bucket.get("input_tokens", 0)),
            "output_tokens": int(bucket.get("output_tokens", 0)),
            "calls": int(bucket.get("calls", 0)),
            "errors": int(bucket.get("error_calls", 0)),
        }

        # Model breakdown
        models = summary.get("models", {})
        model_breakdown = {}
        for model_name, model_data in models.items():
            if period == "today":
                mbucket = model_data.get("daily", {}).get(today_key, {})
            elif period == "week":
                mbucket = model_data.get("weekly", {}).get(week_key, {})
            elif period == "month":
                mbucket = model_data.get("monthly", {}).get(month_key, {})
            else:
                mbucket = model_data.get("all_time", {})
            if mbucket.get("calls", 0) > 0:
                model_breakdown[model_name] = {
                    "usd": round(float(mbucket.get("usd", 0)), 6),
                    "calls": int(mbucket.get("calls", 0)),
                    "input_tokens": int(mbucket.get("input_tokens", 0)),
                    "output_tokens": int(mbucket.get("output_tokens", 0)),
                }
        if model_breakdown:
            result["services"]["sentinel"]["by_model"] = model_breakdown

    except FileNotFoundError:
        result["services"]["sentinel"] = {"error": "No cost data yet"}
    except Exception as e:
        result["services"]["sentinel"] = {"error": str(e)[:200]}

    # --- OpenClaw costs (from gateway usage API) ---
    try:
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        if not token:
            # Try reading from the env file
            env_path = "/root/openclaw/.env"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("OPENCLAW_GATEWAY_TOKEN="):
                            token = line.split("=", 1)[1].strip()
                            break

        if token:
            import urllib.request
            import urllib.error

            url = "http://127.0.0.1:18789/api/sessions.usage.summary"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                data=json.dumps({}).encode(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                oc_data = json.loads(resp.read())
                oc_result = oc_data.get("result", {})
                result["services"]["openclaw"] = {
                    "usd": round(float(oc_result.get("totalCost", 0)), 6),
                    "input_tokens": int(oc_result.get("totalInputTokens", 0)),
                    "output_tokens": int(oc_result.get("totalOutputTokens", 0)),
                    "sessions": int(oc_result.get("totalSessions", 0)),
                }
        else:
            result["services"]["openclaw"] = {"error": "No gateway token available"}
    except Exception as e:
        result["services"]["openclaw"] = {"error": str(e)[:200]}

    # --- Grand total ---
    total_usd = 0.0
    total_input = 0
    total_output = 0
    for svc in result["services"].values():
        if isinstance(svc, dict) and "usd" in svc:
            total_usd += svc["usd"]
            total_input += svc.get("input_tokens", 0)
            total_output += svc.get("output_tokens", 0)

    cop_rate = float(os.environ.get("SENTINEL_USD_TO_COP_RATE", "4000"))
    result["total"] = {
        "usd": round(total_usd, 6),
        "cop": round(total_usd * cop_rate, 2),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "daily_budget_remaining": round(5.0 - total_usd, 6) if period == "today" else None,
    }

    return result


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
        "cost_summary": lambda inp: execute_cost_summary(inp.get("period", "today")),
    }

    executor = executors.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}

    return executor(tool_input)
