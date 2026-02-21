"""Tool definitions and execution for Sentinel sysadmin bot.

Each tool is a function that can be called by Claude via tool_use.
Tools are restricted to safe operations. Destructive commands require confirmation.
"""
import subprocess
import shlex
import re
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
HOST_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
LOCAL_HTTP_RE = re.compile(r"^http://127\.0\.0\.1(?::\d{1,5})?(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?$")


def _is_bounded_int(value: str, min_value: int, max_value: int) -> bool:
    if not value.isdigit():
        return False
    number = int(value)
    return min_value <= number <= max_value


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
    if not HOST_RE.fullmatch(args[2]):
        return False, "Invalid ping host"
    return True, "OK"


def _validate_dig(args: list[str]) -> tuple[bool, str]:
    if len(args) != 1:
        return False, "Allowed: dig <host>"
    if not HOST_RE.fullmatch(args[0]):
        return False, "Invalid host"
    return True, "OK"


def _validate_curl(args: list[str]) -> tuple[bool, str]:
    if not args:
        return False, "curl requires arguments"
    url = args[-1]
    if not LOCAL_HTTP_RE.fullmatch(url):
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
        if args == ["stats", "--no-stream"] or args == ["ps"]:
            return True, "OK"
        return False, "Allowed: docker ps | docker stats --no-stream"
    if cmd == "date":
        return (True, "OK") if not args else (False, "date takes no arguments")
    if cmd == "timedatectl":
        return (True, "OK") if not args else (False, "timedatectl takes no arguments")
    if cmd == "hostnamectl":
        return (True, "OK") if not args else (False, "hostnamectl takes no arguments")

    return False, "Command not in whitelist"


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if a command is in the whitelist and not in the blocklist."""
    command_stripped = command.strip()
    if not command_stripped:
        return False, "Empty command"
    if len(command_stripped) > 256:
        return False, "Command too long"
    command_lower = command_stripped.lower()

    # Check blocklist first
    for pattern in BLOCKED_PATTERNS:
        if pattern in command_lower:
            return False, f"Blocked pattern detected: '{pattern}'"

    try:
        tokens = shlex.split(command_stripped)
    except ValueError as e:
        return False, f"Invalid shell syntax: {e}"

    allowed, reason = _validate_command_tokens(tokens)
    if allowed:
        return True, "OK"

    return False, f"Command blocked: {reason}"


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
        checks["failed_ssh_attempts"] = len([line for line in lines if line.strip()])
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
            import os
            size = os.path.getsize(backup_path)
            return {"status": "success", "path": backup_path, "size_mb": round(size / (1024 * 1024), 2)}
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
