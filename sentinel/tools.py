"""Tool definitions and execution for Sentinel sysadmin bot.

Each tool is a function that can be called by the LLM via function calling.
Tools are restricted to safe operations. Destructive commands require confirmation.
"""
import os
import json
import subprocess
import shlex
import re
import ipaddress
import time
import unicodedata
import psutil
import docker
from typing import Any
from urllib.parse import urlsplit

logger = __import__("logging").getLogger("sentinel")

# Module-level cost tracker reference — set via set_cost_tracker() from sentinel.py.
_cost_tracker_ref: Any = None


def set_cost_tracker(tracker: Any) -> None:
    """Register the APICostTracker instance for use by execute_cost_summary."""
    global _cost_tracker_ref
    _cost_tracker_ref = tracker


# --- TOOL DEFINITIONS (sent to LLM provider) ---

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
        "description": "List Docker containers with status, CPU%, and memory usage.",
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
        "description": "Get comprehensive VPS cost dashboard: Sentinel + OpenClaw + Job Radar costs with per-service and per-model breakdowns. Period: today/week/month/all.",
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
    },
    {
        "name": "check_api_spirals",
        "description": "Detect API usage spirals: container restart loops, error rates, Brave search volume, and cost anomalies. Returns severity: OK, WARNING, or CRITICAL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Lookback window in hours (default 1, max 24)"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_scheduled_tasks",
        "description": "List ALL scheduled tasks across the VPS: system crontab, OpenClaw cron jobs, Job Radar APScheduler jobs, and systemd timers.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "manage_cron",
        "description": "Enable, disable, or check status of cron jobs. Services: openclaw (per-job), jobradar (global pause/resume), system (per-job via crontab).",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "enum": ["openclaw", "jobradar", "system"],
                    "description": "Which cron system to manage"
                },
                "job_name": {
                    "type": "string",
                    "description": "Job name (e.g. news-brief-ai, docker-prune). Not needed for jobradar status."
                },
                "action": {
                    "type": "string",
                    "enum": ["enable", "disable", "status"],
                    "description": "Action to perform"
                }
            },
            "required": ["service", "action"]
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
ALLOWED_DOCKER_CONTAINERS = {"openclaw-openclaw-gateway-1", "job-radar-agent", "job-radar-db"}


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
    if cmd == "crontab":
        return _validate_crontab(args)

    return False, "Command not in whitelist"


def _validate_crontab(args: list[str]) -> tuple[bool, str]:
    """Allow read-only crontab listing: crontab -l, crontab -u <user> -l."""
    if args == ["-l"]:
        return True, "OK"
    if len(args) == 3 and args[0] == "-u" and UNIT_NAME_RE.fullmatch(args[1]) and args[2] == "-l":
        return True, "OK"
    return False, "Allowed: crontab -l, crontab -u <user> -l"


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
    """List explicitly allowed Docker containers with resource stats."""
    try:
        client = docker.from_env()
        containers = []
        for name in sorted(ALLOWED_DOCKER_CONTAINERS):
            try:
                c = client.containers.get(name)
                info: dict[str, Any] = {
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                    "created": str(c.attrs["Created"])[:19],
                }
                if c.status == "running":
                    try:
                        stats = c.stats(stream=False)
                        cpu = stats.get("cpu_stats", {})
                        precpu = stats.get("precpu_stats", {})
                        cpu_delta = (
                            cpu.get("cpu_usage", {}).get("total_usage", 0)
                            - precpu.get("cpu_usage", {}).get("total_usage", 0)
                        )
                        sys_delta = (
                            cpu.get("system_cpu_usage", 0)
                            - precpu.get("system_cpu_usage", 0)
                        )
                        n_cpus = cpu.get("online_cpus", 1)
                        if sys_delta > 0:
                            info["cpu_percent"] = round(
                                (cpu_delta / sys_delta) * n_cpus * 100, 1
                            )
                        mem = stats.get("memory_stats", {})
                        usage = mem.get("usage", 0)
                        limit = mem.get("limit", 0)
                        if usage:
                            info["memory_mb"] = round(usage / (1024**2), 1)
                        if limit:
                            info["memory_limit_mb"] = round(limit / (1024**2), 0)
                    except Exception:
                        pass  # Stats unavailable — just skip
                containers.append(info)
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

    # UFW status (requires sudo — sentinel user has a sudoers entry for ufw)
    try:
        ufw = subprocess.run(["sudo", "-n", "ufw", "status", "verbose"], capture_output=True, text=True, timeout=10)
        if ufw.returncode == 0:
            checks["ufw"] = ufw.stdout[:500]
        else:
            checks["ufw"] = ufw.stderr[:200] if ufw.stderr else "UFW returned non-zero"
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

        # HTTP health probe — exec inside container (host can't reach gateway port)
        try:
            probe_result = container.exec_run(
                ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:18789/"],
                demux=True,
            )
            stdout = (probe_result.output[0] or b"").decode("utf-8", errors="replace").strip()
            health["http_probe_status"] = stdout or "000"
        except Exception:
            health["http_probe_status"] = "exec_failed"

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


def _read_gateway_internal_log(
    container, since_hours: int = 24
) -> list[dict[str, str]]:
    """Read OpenClaw gateway's internal JSON log from inside the container.

    The gateway writes detailed session data (run starts/ends, durations,
    errors, tool calls) to /tmp/openclaw/openclaw-{date}.log.
    Docker stdout only has startup messages and Telegram send confirmations.

    Returns list of dicts: {"msg": str, "time": str, "level": str}.
    Time-windowed: only entries within the last ``since_hours`` are returned.
    Reads yesterday's log too when the lookback window crosses midnight.
    """
    import datetime as _dt

    entries: list[dict[str, str]] = []
    now = _dt.datetime.now(_dt.timezone.utc)
    cutoff_str = (now - _dt.timedelta(hours=since_hours)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    # Determine which daily log files to read
    dates = [now.strftime("%Y-%m-%d")]
    if since_hours > (now.hour + now.minute / 60 + 1):
        yesterday = (now - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        dates.insert(0, yesterday)

    for date_str in dates:
        try:
            result = container.exec_run(
                ["cat", f"/tmp/openclaw/openclaw-{date_str}.log"],
                demux=True,
            )
            if result.exit_code != 0 or not result.output[0]:
                continue
            for raw_line in result.output[0].decode(
                "utf-8", errors="replace"
            ).splitlines():
                try:
                    obj = json.loads(raw_line.strip())
                    ts = str(obj.get("time", ""))
                    # Time-window filter (compare first 19 chars: YYYY-MM-DDTHH:MM:SS)
                    if ts and ts[:19] < cutoff_str:
                        continue
                    entries.append({
                        "msg": str(obj.get("1", "")),
                        "time": ts,
                        "level": (
                            obj.get("_meta", {}).get("logLevelName", "")
                        ),
                    })
                except (json.JSONDecodeError, AttributeError):
                    continue
        except Exception:
            continue

    return entries


# Brave Search API cost per query (USD).
# Source: brave.com/search/api — $5 per 1,000 queries ($0.005/query), 1,000 free/month.
_BRAVE_COST_PER_QUERY = 0.005


def _parse_docker_logs_costs(container_name: str, since_hours: int = 24) -> dict[str, Any]:
    """Parse Docker container logs to extract API call counts and estimate costs.

    Supports OpenClaw gateway logs (run start/done entries) and
    Job Radar logs (httpx Gemini API call entries).
    """
    import datetime as _dt

    result: dict[str, Any] = {"runs": 0, "models": {}, "errors": 0, "brave_calls": 0}

    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        result["status"] = container.status
        result["started_at"] = str(container.attrs.get("State", {}).get("StartedAt", ""))[:19]

        since_ts = int(time.time()) - (since_hours * 3600)
        log_text = container.logs(since=since_ts, tail=5000).decode("utf-8", errors="replace")
        lines = log_text.splitlines()
        result["log_lines_scanned"] = len(lines)

        if container_name == "openclaw-openclaw-gateway-1":
            # Use shared helper to read internal JSON log (has all run data).
            # Docker stdout only has startup messages and Telegram send confirmations.
            entries = _read_gateway_internal_log(container, since_hours=since_hours)
            result["log_lines_scanned"] = len(entries)
            for entry in entries:
                msg = entry["msg"]
                if "embedded run start" in msg:
                    result["runs"] += 1
                    for part in msg.split():
                        if part.startswith("model="):
                            model = part.split("=", 1)[1]
                            result["models"][model] = result["models"].get(model, 0) + 1
                elif "isError=true" in msg:
                    result["errors"] += 1
                elif "brave" in msg.lower() or "web_search" in msg.lower():
                    result["brave_calls"] += 1

        elif container_name == "job-radar-agent":
            # Parse Job Radar httpx Gemini API calls
            _model_re = re.compile(r"models/([^:]+):generateContent")
            for line in lines:
                if "generateContent" in line:
                    result["runs"] += 1
                    model_match = _model_re.search(line)
                    if model_match:
                        model = model_match.group(1)
                        result["models"][model] = result["models"].get(model, 0) + 1
                    else:
                        result["models"]["gemini-2.5-flash"] = result["models"].get("gemini-2.5-flash", 0) + 1
                elif "brave" in line.lower():
                    result["brave_calls"] += 1
                elif "error" in line.lower() and "api" in line.lower():
                    result["errors"] += 1

    except docker.errors.NotFound:
        result["status"] = "not_found"
    except docker.errors.DockerException as e:
        result["status"] = f"error: {str(e)[:100]}"

    return result


# Average tokens per run by model (conservative estimates for cost estimation).
# Based on observed patterns: OpenClaw cron briefs use more tokens; interactive is lighter.
_AVG_TOKENS_PER_RUN = {
    "gemini-2.5-flash": {"input": 2000, "output": 500},
    "gemini-2.5-pro": {"input": 3000, "output": 800},
    "claude-sonnet-4-6": {"input": 2500, "output": 600},
    "claude-haiku-4-5": {"input": 1500, "output": 400},
    # Codex: subscription-covered via OAuth — $0 per-token cost.
    "gpt-5.3-codex": {"input": 2000, "output": 500},
}
# Pricing per 1M tokens (USD). Updated 2026-03-02 (verified against official APIs).
_MODEL_COST_PER_M = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    # Codex: $0 — subscription-covered, not pay-per-token.
    "gpt-5.3-codex": {"input": 0.0, "output": 0.0},
}

# Job Radar descriptions and static fallback (used when API is unreachable).
_JR_DESCRIPTIONS = {
    "discovery_sync": "Scrape job boards for new listings",
    "digest_am": "Morning job matches → Telegram",
    "digest_pm": "Evening job matches → Telegram",
    "watchlist_sync": "Check watchlist companies for new posts",
    "cleanup": "Remove expired listings (>21 days)",
    "weekly_report": "Weekly stats summary → Telegram",
}
_JR_FALLBACK = [
    {"id": "discovery_sync", "schedule": "0 5,17 * * *", "paused": False},
    {"id": "digest_am", "schedule": "0 13 * * *", "paused": False},
    {"id": "digest_pm", "schedule": "0 23 * * *", "paused": False},
    {"id": "watchlist_sync", "schedule": "0 7 * * *", "paused": False},
    {"id": "cleanup", "schedule": "0 4 * * *", "paused": False},
    {"id": "weekly_report", "schedule": "0 23 * * 6", "paused": False},
]

# System crontab job patterns for manage_cron tool.
_SYSTEM_JOB_PATTERNS = {
    "docker-prune": "docker builder prune",
    "openclaw-backup": "backup",
    "log-cleanup": ".bak",
}


def _estimate_docker_service_cost(parsed: dict[str, Any]) -> dict[str, Any]:
    """Estimate USD cost from parsed Docker log data."""
    total_usd = 0.0
    est_input = 0
    est_output = 0
    model_details = {}

    for model, count in parsed.get("models", {}).items():
        avg = _AVG_TOKENS_PER_RUN.get(model, {"input": 2000, "output": 500})
        pricing = _MODEL_COST_PER_M.get(model, {"input": 0.30, "output": 2.50})
        in_tokens = avg["input"] * count
        out_tokens = avg["output"] * count
        cost = (in_tokens * pricing["input"] + out_tokens * pricing["output"]) / 1_000_000
        total_usd += cost
        est_input += in_tokens
        est_output += out_tokens
        model_details[model] = {
            "runs": count,
            "est_input_tokens": in_tokens,
            "est_output_tokens": out_tokens,
            "est_usd": round(cost, 6),
        }

    # Add Brave API cost ($0.005/query)
    brave_calls = parsed.get("brave_calls", 0)
    brave_usd = round(brave_calls * _BRAVE_COST_PER_QUERY, 6)
    total_usd += brave_usd

    return {
        "est_usd": round(total_usd, 6),
        "est_input_tokens": est_input,
        "est_output_tokens": est_output,
        "runs": parsed.get("runs", 0),
        "errors": parsed.get("errors", 0),
        "brave_calls": brave_calls,
        "brave_est_usd": brave_usd,
        "status": parsed.get("status", "unknown"),
        "started_at": parsed.get("started_at", ""),
        "by_model": model_details,
        "is_estimate": True,
    }


_VPS_COST_CACHE_PATH = "/var/log/sentinel/vps-cost-cache.json"


def _load_vps_cost_cache() -> dict[str, Any]:
    """Load the persistent VPS cost cache (Docker-derived cost data)."""
    try:
        with open(_VPS_COST_CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_vps_cost_cache(cache: dict[str, Any]) -> None:
    """Atomically save the VPS cost cache."""
    import tempfile
    cache_dir = os.path.dirname(_VPS_COST_CACHE_PATH)
    os.makedirs(cache_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".vps-cost-cache.", suffix=".json", dir=cache_dir)
    os.close(fd)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp_path, 0o640)
        os.replace(tmp_path, _VPS_COST_CACHE_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _merge_docker_costs_to_cache(
    cache: dict[str, Any],
    service: str,
    parsed: dict[str, Any],
    day_key: str,
) -> None:
    """Merge freshly parsed Docker log costs into the persistent cache.

    Stores per-day snapshots so historical data survives container restarts.
    """
    svc_cache = cache.setdefault(service, {})
    day_cache = svc_cache.setdefault(day_key, {
        "runs": 0, "errors": 0, "brave_calls": 0, "models": {},
    })

    # Update with latest parsed values (Docker logs are the source of truth for today)
    day_cache["runs"] = max(day_cache["runs"], parsed.get("runs", 0))
    day_cache["errors"] = max(day_cache["errors"], parsed.get("errors", 0))
    day_cache["brave_calls"] = max(day_cache["brave_calls"], parsed.get("brave_calls", 0))
    day_cache["status"] = parsed.get("status", "unknown")
    day_cache["started_at"] = parsed.get("started_at", "")

    for model, count in parsed.get("models", {}).items():
        day_cache["models"][model] = max(day_cache["models"].get(model, 0), count)


def _get_cached_costs(
    cache: dict[str, Any],
    service: str,
    period: str,
    now: "datetime",
) -> dict[str, Any]:
    """Get cost data from cache for a given service and period.

    Aggregates across multiple days for week/month/all periods.
    """
    import datetime as _dt

    svc_cache = cache.get(service, {})
    if not svc_cache:
        return {"runs": 0, "errors": 0, "brave_calls": 0, "models": {}, "status": "unknown", "started_at": ""}

    # Determine which days to include
    today = now.date()
    if period == "today":
        day_keys = [today.isoformat()]
    elif period == "week":
        start = today - _dt.timedelta(days=today.weekday())
        day_keys = [(start + _dt.timedelta(days=i)).isoformat() for i in range((today - start).days + 1)]
    elif period == "month":
        day_keys = [f"{today.year}-{today.month:02d}-{d:02d}" for d in range(1, today.day + 1)]
    else:
        day_keys = list(svc_cache.keys())

    aggregated = {"runs": 0, "errors": 0, "brave_calls": 0, "models": {}, "status": "unknown", "started_at": ""}

    for dk in day_keys:
        day_data = svc_cache.get(dk, {})
        if not day_data:
            continue
        aggregated["runs"] += day_data.get("runs", 0)
        aggregated["errors"] += day_data.get("errors", 0)
        aggregated["brave_calls"] += day_data.get("brave_calls", 0)
        aggregated["status"] = day_data.get("status", aggregated["status"])
        aggregated["started_at"] = day_data.get("started_at", aggregated["started_at"])
        for model, count in day_data.get("models", {}).items():
            aggregated["models"][model] = aggregated["models"].get(model, 0) + count

    return aggregated


def execute_cost_summary(period: str = "today", cost_tracker: Any = None) -> dict[str, Any]:
    """Get comprehensive VPS cost dashboard: Sentinel + OpenClaw + Job Radar.

    Sentinel costs are exact (from JSONL event log).
    OpenClaw and Job Radar costs are estimated from Docker log API call counts.
    Historical data is persisted in a cache file so it survives container restarts.

    Args:
        period: "today", "week", "month", or "all".
        cost_tracker: Optional APICostTracker instance for locked reads.
    """
    import datetime as _dt

    result: dict[str, Any] = {"period": period, "services": {}}
    now = _dt.datetime.now(_dt.timezone.utc)

    # Determine lookback hours based on period
    if period == "today":
        hours_since_midnight = now.hour + now.minute / 60
        since_hours = max(1, int(hours_since_midnight) + 1)
    elif period == "week":
        since_hours = min(168, 24 * (now.weekday() + 1))
    elif period == "month":
        since_hours = min(744, 24 * now.day)
    else:
        since_hours = 720  # ~30 days for "all" (Docker logs don't persist forever)

    # --- Sentinel costs (EXACT — from cost tracker or summary JSON) ---
    tracker = cost_tracker or _cost_tracker_ref
    try:
        if tracker is not None and hasattr(tracker, "get_summary"):
            # Preferred: use the tracker's thread-safe get_summary() — avoids raw file open
            tracker_data = tracker.get_summary(period)
            sentinel_data: dict[str, Any] = {
                "usd": round(float(tracker_data.get("usd", 0)), 6),
                "input_tokens": int(tracker_data.get("input_tokens", 0)),
                "output_tokens": int(tracker_data.get("output_tokens", 0)),
                "calls": int(tracker_data.get("calls", 0)),
                "errors": int(tracker_data.get("errors", 0)),
                "is_estimate": False,
            }
            by_model = tracker_data.get("by_model")
            if by_model:
                sentinel_data["by_model"] = by_model
            result["services"]["sentinel"] = sentinel_data
        else:
            # Fallback: read the summary JSON directly
            sentinel_summary_path = "/var/log/sentinel/api-cost-summary.json"
            with open(sentinel_summary_path) as f:
                summary = json.load(f)

            totals = summary.get("totals", {})
            today_key = now.strftime("%Y-%m-%d")
            week_key = now.strftime("%G-W%V")
            month_key = now.strftime("%Y-%m")

            if period == "today":
                bucket = totals.get("daily", {}).get(today_key, {})
            elif period == "week":
                bucket = totals.get("weekly", {}).get(week_key, {})
            elif period == "month":
                bucket = totals.get("monthly", {}).get(month_key, {})
            else:
                bucket = totals.get("all_time", {})

            sentinel_data = {
                "usd": round(float(bucket.get("usd", 0)), 6),
                "input_tokens": int(bucket.get("input_tokens", 0)),
                "output_tokens": int(bucket.get("output_tokens", 0)),
                "calls": int(bucket.get("calls", 0)),
                "errors": int(bucket.get("error_calls", 0)),
                "is_estimate": False,
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
                sentinel_data["by_model"] = model_breakdown

            result["services"]["sentinel"] = sentinel_data

    except FileNotFoundError:
        result["services"]["sentinel"] = {"error": "No cost data yet", "is_estimate": False}
    except Exception as e:
        logger.error("cost_summary sentinel section failed: %s", e, exc_info=True)
        result["services"]["sentinel"] = {"error": str(e)[:200], "is_estimate": False}

    # --- OpenClaw & Job Radar costs (ESTIMATED — from Docker logs + persistent cache) ---
    vps_cache = _load_vps_cost_cache()
    today_key = now.strftime("%Y-%m-%d")

    # Parse fresh Docker logs for today and merge into cache
    oc_parsed = _parse_docker_logs_costs("openclaw-openclaw-gateway-1", since_hours=since_hours)
    _merge_docker_costs_to_cache(vps_cache, "openclaw", oc_parsed, today_key)

    jr_parsed = _parse_docker_logs_costs("job-radar-agent", since_hours=since_hours)
    _merge_docker_costs_to_cache(vps_cache, "job_radar", jr_parsed, today_key)

    # Persist cache atomically
    _save_vps_cost_cache(vps_cache)

    # Get aggregated data for the requested period (uses cache for historical days)
    oc_cached = _get_cached_costs(vps_cache, "openclaw", period, now)
    result["services"]["openclaw"] = _estimate_docker_service_cost(oc_cached)

    jr_cached = _get_cached_costs(vps_cache, "job_radar", period, now)
    result["services"]["job_radar"] = _estimate_docker_service_cost(jr_cached)

    # --- Grand totals ---
    total_usd = 0.0
    total_est_usd = 0.0
    total_input = 0
    total_output = 0
    total_runs = 0
    total_errors = 0
    total_brave = 0
    has_estimates = False

    for svc_name, svc in result["services"].items():
        if not isinstance(svc, dict) or "error" in svc:
            continue
        is_est = svc.get("is_estimate", False)
        cost_key = "est_usd" if is_est else "usd"
        input_key = "est_input_tokens" if is_est else "input_tokens"
        output_key = "est_output_tokens" if is_est else "output_tokens"

        cost = float(svc.get(cost_key, 0))
        total_usd += cost
        if is_est:
            total_est_usd += cost
            has_estimates = True
        total_input += int(svc.get(input_key, 0))
        total_output += int(svc.get(output_key, 0))
        total_runs += int(svc.get("runs", svc.get("calls", 0)))
        total_errors += int(svc.get("errors", 0))
        total_brave += int(svc.get("brave_calls", 0))

    cop_rate = float(os.environ.get("SENTINEL_USD_TO_COP_RATE", "4000"))
    result["total"] = {
        "usd": round(total_usd, 6),
        "cop": round(total_usd * cop_rate, 2),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_runs": total_runs,
        "total_errors": total_errors,
        "total_brave_calls": total_brave,
        "has_estimates": has_estimates,
        "daily_budget": 5.0,
        "daily_budget_remaining": round(5.0 - total_usd, 6) if period == "today" else None,
        "budget_pct_used": round((total_usd / 5.0) * 100, 2) if period == "today" else None,
    }

    return result


def execute_check_api_spirals(hours: int = 1) -> dict[str, Any]:
    """Detect API usage spirals across the VPS."""
    hours = max(1, min(hours, 24))
    alerts: list[str] = []
    metrics: dict[str, Any] = {"lookback_hours": hours}
    severity = "OK"

    # 1. Gateway container restart count
    try:
        client = docker.from_env()
        container = client.containers.get("openclaw-openclaw-gateway-1")
        restart_count = container.attrs.get("RestartCount", 0)
        state = container.attrs.get("State", {})
        started_at = state.get("StartedAt", "")
        metrics["gateway"] = {
            "status": container.status,
            "restart_count": restart_count,
            "started_at": started_at[:19],
        }
        if restart_count > 3:
            alerts.append(f"CRITICAL: Gateway restarted {restart_count} times (total)")
            severity = "CRITICAL"
        elif restart_count > 1:
            alerts.append(f"WARNING: Gateway restarted {restart_count} times (total)")
            if severity != "CRITICAL":
                severity = "WARNING"
    except docker.errors.NotFound:
        metrics["gateway"] = {"status": "not_found"}
        alerts.append("CRITICAL: Gateway container not found")
        severity = "CRITICAL"
    except docker.errors.DockerException as e:
        metrics["gateway"] = {"error": str(e)[:200]}

    # 2. Scan gateway INTERNAL log for errors, Brave usage, and run durations.
    #    Docker stdout only has startup messages — all run data is in the
    #    internal JSON log at /tmp/openclaw/openclaw-{date}.log inside the container.
    try:
        container = client.containers.get("openclaw-openclaw-gateway-1")
        entries = _read_gateway_internal_log(container, since_hours=hours)

        error_count = 0
        brave_count = 0
        overflow_count = 0
        loop_detect_count = 0
        run_count = 0
        run_durations: list[int] = []
        aborted_runs = 0
        models_seen: dict[str, int] = {}

        for entry in entries:
            msg = entry["msg"]
            level = entry["level"]
            lower = msg.lower()

            # Count errors from log level (most reliable) and message content
            if level in ("ERROR", "FATAL"):
                error_count += 1
            elif "isError=true" in msg:
                error_count += 1

            # Brave / web_search tool calls
            if "brave" in lower or "web_search" in lower:
                brave_count += 1

            # Loop detection events (tool-call loop guardrail)
            if any(kw in lower for kw in [
                "loop detect", "circuit breaker", "tool loop",
                "loop warning", "loop critical",
            ]):
                loop_detect_count += 1

            # Context overflow detection
            if any(kw in lower for kw in [
                "overflow", "low context window", "context exceeded",
                "token budget", "context pruning",
            ]):
                overflow_count += 1

            # Run start: count runs and track models
            if "embedded run start" in msg:
                run_count += 1
                for part in msg.split():
                    if part.startswith("model="):
                        model = part.split("=", 1)[1]
                        models_seen[model] = models_seen.get(model, 0) + 1

            # Run done: extract duration and abort status
            if "embedded run done" in msg:
                m = re.search(r"durationMs=(\d+)", msg)
                if m:
                    run_durations.append(int(m.group(1)))
                if "aborted=true" in msg:
                    aborted_runs += 1

        metrics["gateway_logs"] = {
            "entries_scanned": len(entries),
            "error_count": error_count,
            "brave_calls": brave_count,
            "brave_est_usd": round(brave_count * _BRAVE_COST_PER_QUERY, 6),
            "loop_detection_events": loop_detect_count,
            "context_overflow_warnings": overflow_count,
            "runs": run_count,
            "aborted_runs": aborted_runs,
            "models": models_seen,
        }

        # Run duration analysis
        if run_durations:
            max_run = max(run_durations)
            avg_run = sum(run_durations) / len(run_durations)
            metrics["gateway_runs"] = {
                "count": len(run_durations),
                "avg_ms": round(avg_run),
                "max_ms": max_run,
                "min_ms": min(run_durations),
            }
            if max_run > 120000:
                alerts.append(f"CRITICAL: Gateway run exceeded 120s ({max_run}ms)")
                severity = "CRITICAL"
            elif max_run > 60000:
                alerts.append(f"WARNING: Longest gateway run {max_run}ms (possible spiral)")
                if severity != "CRITICAL":
                    severity = "WARNING"
            # Burst detection
            if len(run_durations) > 50:
                alerts.append(
                    f"WARNING: {len(run_durations)} gateway runs in {hours}h (high activity)"
                )
                if severity != "CRITICAL":
                    severity = "WARNING"
        elif run_count > 0:
            # Runs detected but no "done" entries — possible stuck runs
            alerts.append(
                f"WARNING: {run_count} runs started but 0 completed in {hours}h (possible stuck runs)"
            )
            if severity != "CRITICAL":
                severity = "WARNING"

        # Aborted run detection
        if aborted_runs > 0:
            alerts.append(f"WARNING: {aborted_runs} aborted runs in {hours}h")
            if severity != "CRITICAL":
                severity = "WARNING"

        # Rate-based error thresholds (per hour)
        error_rate = error_count / max(hours, 1)
        if error_rate > 50:
            alerts.append(f"CRITICAL: {error_rate:.0f} errors/hour in gateway logs")
            severity = "CRITICAL"
        elif error_rate > 10:
            alerts.append(f"WARNING: {error_rate:.0f} errors/hour in gateway logs")
            if severity != "CRITICAL":
                severity = "WARNING"

        if brave_count > 30:
            alerts.append(
                f"WARNING: {brave_count} Brave/search calls in {hours}h "
                f"(~${brave_count * _BRAVE_COST_PER_QUERY:.3f})"
            )
            if severity != "CRITICAL":
                severity = "WARNING"

        if loop_detect_count > 0:
            alerts.append(
                f"WARNING: {loop_detect_count} tool-loop detection events in {hours}h "
                f"(circuit breaker may have killed runs)"
            )
            if severity != "CRITICAL":
                severity = "WARNING"

        if overflow_count > 0:
            alerts.append(f"WARNING: {overflow_count} context overflow warnings in {hours}h")
            if severity != "CRITICAL":
                severity = "WARNING"

    except Exception as e:
        metrics["gateway_logs"] = {"error": str(e)[:200]}

    # 3. Check Sentinel cost for anomalies
    try:
        summary_path = "/var/log/sentinel/api-cost-summary.json"
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                summary = json.load(f)
            import datetime as _dt
            today_key = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
            daily = summary.get("totals", {}).get("daily", {}).get(today_key, {})
            today_usd = float(daily.get("usd", 0))
            today_calls = int(daily.get("calls", 0))
            today_errors = int(daily.get("error_calls", 0))
            metrics["sentinel_today"] = {
                "usd": round(today_usd, 6),
                "calls": today_calls,
                "errors": today_errors,
            }
            if today_usd > 1.0:
                alerts.append(f"WARNING: Sentinel daily spend ${today_usd:.4f} exceeds $1.00")
                if severity != "CRITICAL":
                    severity = "WARNING"
            if today_errors > 10:
                alerts.append(f"WARNING: Sentinel {today_errors} API errors today")
                if severity != "CRITICAL":
                    severity = "WARNING"
        else:
            metrics["sentinel_today"] = {"status": "no cost data file"}
    except Exception as e:
        metrics["sentinel_today"] = {"error": str(e)[:200]}

    # 4. Check OpenClaw gateway health (no REST usage API — WebSocket only)
    try:
        oc_container = client.containers.get("openclaw-openclaw-gateway-1")
        oc_health = oc_container.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")
        metrics["openclaw_health"] = {
            "status": oc_container.status,
            "docker_health": oc_health,
        }
    except Exception as e:
        metrics["openclaw_health"] = {"error": str(e)[:200]}

    return {
        "severity": severity,
        "alerts": alerts if alerts else ["All metrics within normal bounds."],
        "metrics": metrics,
    }


def execute_list_scheduled_tasks() -> dict[str, Any]:
    """List all scheduled tasks across the VPS."""
    from pathlib import Path

    tasks: dict[str, Any] = {}

    # 1. System crontab — check /etc/crontab, /etc/cron.d/*, and user crontabs
    all_cron_lines: list[str] = []
    try:
        # /etc/crontab (system-wide)
        etc_crontab = Path("/etc/crontab")
        if etc_crontab.exists():
            for line in etc_crontab.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("SHELL") and not stripped.startswith("PATH") and not stripped.startswith("MAILTO"):
                    all_cron_lines.append(f"[system] {stripped}")
    except OSError:
        pass

    try:
        # Root's personal crontab (via sudo — sentinel has sudoers entry for crontab -l)
        root_cron = subprocess.run(
            ["sudo", "-n", "crontab", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        if root_cron.returncode == 0:
            for line in root_cron.stdout.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    all_cron_lines.append(f"[root] {stripped}")
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        # /etc/cron.d/* (package-installed cron jobs)
        cron_d = Path("/etc/cron.d")
        if cron_d.is_dir():
            for cf in sorted(cron_d.iterdir()):
                if cf.is_file() and not cf.name.startswith("."):
                    try:
                        for line in cf.read_text(encoding="utf-8", errors="replace").splitlines():
                            stripped = line.strip()
                            if stripped and not stripped.startswith("#") and not stripped.startswith("SHELL") and not stripped.startswith("PATH"):
                                all_cron_lines.append(f"[{cf.name}] {stripped}")
                    except OSError:
                        pass
    except OSError:
        pass

    tasks["system_crontab"] = {
        "count": len(all_cron_lines),
        "jobs": all_cron_lines[:20],
    }

    # 2. OpenClaw cron jobs (from jobs.json — check host mount and container)
    oc_cron_loaded = False
    for oc_cron_path in ["/root/.openclaw/cron/jobs.json"]:
        try:
            if os.path.exists(oc_cron_path):
                with open(oc_cron_path) as f:
                    oc_cron = json.load(f)
                jobs = oc_cron.get("jobs", [])
                tasks["openclaw_cron"] = {
                    "count": len(jobs),
                    "jobs": [
                        {
                            "name": j.get("name", j.get("id", "?")[:12]),
                            "description": j.get("description", ""),
                            "enabled": j.get("enabled", True),
                            "schedule": j.get("schedule", {}).get("expr", str(j.get("schedule", "?"))),
                            "tz": j.get("schedule", {}).get("tz", "UTC"),
                            "model": j.get("payload", {}).get("model", "default"),
                            "command": j.get("payload", {}).get("message", ""),
                            "delivery": j.get("delivery", {}).get("channel", ""),
                        }
                        for j in jobs[:20]
                    ],
                }
                if not jobs:
                    tasks["openclaw_cron"]["note"] = "No cron jobs configured"
                oc_cron_loaded = True
                break
        except Exception:
            pass
    if not oc_cron_loaded:
        tasks["openclaw_cron"] = {"count": 0, "note": "Cron config not accessible"}

    # Also check root's crontab for OpenClaw-related jobs
    try:
        root_cron = subprocess.run(
            ["sudo", "-n", "crontab", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        if root_cron.returncode == 0:
            oc_cron_entries = []
            for line in root_cron.stdout.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "openclaw" in stripped.lower():
                    oc_cron_entries.append(stripped)
            if oc_cron_entries:
                existing_jobs = tasks.get("openclaw_cron", {}).get("jobs", [])
                for entry in oc_cron_entries:
                    # Parse cron expression from the line (first 5 fields)
                    parts = entry.split(None, 5)
                    cron_expr = " ".join(parts[:5]) if len(parts) >= 5 else entry[:30]
                    cmd_part = parts[5] if len(parts) > 5 else ""
                    # Derive a short name from the command
                    if "backup" in cmd_part.lower():
                        sname = "openclaw-backup"
                    elif "find" in cmd_part.lower() and "delete" in cmd_part.lower():
                        sname = "log-cleanup"
                    else:
                        sname = "system-cron"
                    existing_jobs.append({
                        "name": sname,
                        "description": cmd_part[:80],
                        "enabled": True,
                        "schedule": cron_expr,
                        "tz": "UTC",
                        "model": "",
                        "command": "",
                        "delivery": "host",
                    })
                tasks["openclaw_cron"]["count"] = len(existing_jobs)
                tasks["openclaw_cron"]["jobs"] = existing_jobs
                # Replace misleading note if host crontab has openclaw entries
                if tasks["openclaw_cron"].get("note") == "No cron jobs configured":
                    tasks["openclaw_cron"]["note"] = "Host crontab only (no gateway cron)"
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 3. Job Radar APScheduler jobs — live status from API
    jr_jobs = None
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:8080/api/v1/scheduler/status", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            jr_data = json.loads(resp.read().decode())
        if jr_data.get("running"):
            jr_jobs = jr_data.get("jobs", [])
    except Exception:
        pass  # API unreachable — use fallback

    if jr_jobs is None:
        jr_jobs = _JR_FALLBACK

    tasks["job_radar_scheduler"] = {
        "count": len(jr_jobs),
        "jobs": [
            {
                "id": j.get("id", "?"),
                "schedule": j.get("schedule", "?"),
                "paused": j.get("paused", False),
                "desc": _JR_DESCRIPTIONS.get(j.get("id", ""), ""),
            }
            for j in jr_jobs
        ],
    }

    # 4. Systemd timers
    try:
        timers_result = subprocess.run(
            ["systemctl", "list-timers", "--no-pager"],
            capture_output=True, text=True, timeout=10,
        )
        if timers_result.returncode == 0:
            timer_lines = [
                line.strip() for line in timers_result.stdout.splitlines()
                if ".timer" in line
            ]
            tasks["systemd_timers"] = {
                "count": len(timer_lines),
                "timers": timer_lines[:15],
            }
        else:
            tasks["systemd_timers"] = {"count": 0, "note": "Could not list timers"}
    except Exception as e:
        tasks["systemd_timers"] = {"error": str(e)[:200]}

    return tasks


def execute_manage_cron(service: str, action: str, job_name: str = "") -> dict[str, Any]:
    """Enable, disable, or check status of cron jobs across VPS services."""
    import urllib.request

    if service == "openclaw":
        # --- OpenClaw cron: per-job enable/disable via jobs.json ---
        cron_path = "/root/.openclaw/cron/jobs.json"
        try:
            with open(cron_path) as f:
                data = json.load(f)
        except Exception as e:
            return {"error": f"Cannot read {cron_path}: {e}"}

        jobs = data.get("jobs", [])

        if action == "status":
            return {
                "service": "openclaw",
                "jobs": [
                    {"name": j.get("name", "?"), "enabled": j.get("enabled", True)}
                    for j in jobs
                ],
            }

        if not job_name:
            return {"error": "job_name required for openclaw enable/disable"}

        target = None
        for j in jobs:
            if j.get("name") == job_name:
                target = j
                break
        if not target:
            names = [j.get("name", "?") for j in jobs]
            return {"error": f"Job '{job_name}' not found. Available: {names}"}

        new_state = action == "enable"
        target["enabled"] = new_state

        try:
            with open(cron_path, "w") as f:
                json.dump(data, f, indent=2)
            # Fix ownership (Edit/write resets to root:root)
            subprocess.run(
                ["chown", "sentinel:systemd-journal", cron_path],
                capture_output=True, timeout=5,
            )
            # Reload gateway config
            client = docker.from_env()
            client.containers.get("openclaw-openclaw-gateway-1").kill(signal="SIGUSR1")
        except Exception as e:
            return {"error": f"Updated file but reload failed: {e}"}

        return {"ok": True, "service": "openclaw", "job": job_name, "enabled": new_state}

    elif service == "jobradar":
        # --- Job Radar: global pause/resume via REST API ---
        base = "http://localhost:8080/api/v1/scheduler"
        try:
            if action == "status":
                req = urllib.request.Request(f"{base}/status", method="GET")
            elif action == "disable":
                req = urllib.request.Request(f"{base}/pause", method="POST")
            elif action == "enable":
                req = urllib.request.Request(f"{base}/resume", method="POST")
            else:
                return {"error": f"Invalid action: {action}"}

            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
            return {"ok": True, "service": "jobradar", "action": action, "result": result}
        except Exception as e:
            return {"error": f"Job Radar API error: {e}"}

    elif service == "system":
        # --- System crontab: comment/uncomment lines ---
        if action == "status":
            try:
                result = subprocess.run(
                    ["sudo", "-n", "crontab", "-l"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    return {"error": "Cannot read crontab"}
                jobs = []
                for line in result.stdout.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("SHELL") or stripped.startswith("PATH") or stripped.startswith("MAILTO"):
                        continue
                    is_disabled = stripped.startswith("#SENTINEL_DISABLED#")
                    clean = stripped.replace("#SENTINEL_DISABLED#", "", 1).strip()
                    # Try to identify the job
                    name = "unknown"
                    for jname, pattern in _SYSTEM_JOB_PATTERNS.items():
                        if pattern in clean.lower():
                            name = jname
                            break
                    if name == "unknown" and not clean.startswith("#"):
                        # Generic active cron line
                        parts = clean.split(None, 5)
                        name = parts[5][:40] if len(parts) > 5 else clean[:40]
                    if clean.startswith("#"):
                        continue  # Skip real comments
                    jobs.append({"name": name, "enabled": not is_disabled, "line": clean[:60]})
                return {"service": "system", "jobs": jobs}
            except Exception as e:
                return {"error": f"Cannot read crontab: {e}"}

        if not job_name:
            return {"error": "job_name required for system enable/disable"}

        pattern = _SYSTEM_JOB_PATTERNS.get(job_name)
        if not pattern:
            return {"error": f"Unknown system job '{job_name}'. Known: {list(_SYSTEM_JOB_PATTERNS.keys())}"}

        try:
            result = subprocess.run(
                ["sudo", "-n", "crontab", "-l"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return {"error": "Cannot read crontab"}

            lines = result.stdout.splitlines()
            found = False
            new_lines = []
            for line in lines:
                if pattern in line.lower():
                    found = True
                    clean = line.replace("#SENTINEL_DISABLED#", "", 1).strip()
                    if action == "disable":
                        new_lines.append(f"#SENTINEL_DISABLED# {clean}")
                    else:  # enable
                        new_lines.append(clean)
                else:
                    new_lines.append(line)

            if not found:
                return {"error": f"No crontab line matches job '{job_name}'"}

            # Write back via sudo crontab -
            new_crontab = "\n".join(new_lines) + "\n"
            write_result = subprocess.run(
                ["sudo", "-n", "crontab", "-"],
                input=new_crontab, capture_output=True, text=True, timeout=10,
            )
            if write_result.returncode != 0:
                return {"error": f"Failed to write crontab: {write_result.stderr[:200]}"}

            return {"ok": True, "service": "system", "job": job_name, "enabled": action == "enable"}
        except Exception as e:
            return {"error": f"Crontab management error: {e}"}

    else:
        return {"error": f"Unknown service: {service}. Valid: openclaw, jobradar, system"}


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
        "check_api_spirals": lambda inp: execute_check_api_spirals(inp.get("hours", 1)),
        "list_scheduled_tasks": lambda _: execute_list_scheduled_tasks(),
        "manage_cron": lambda inp: execute_manage_cron(inp["service"], inp["action"], inp.get("job_name", "")),
    }

    executor = executors.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}

    return executor(tool_input)
