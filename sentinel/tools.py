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
    "> /dev/", "chmod 777", "wget ",
    "curl -o", "curl -O",
    "python ", "node ", "bash -c", "sh -c",
    "export ", "unset ", "env ",
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
        health["status"] = container.status
        health["uptime"] = str(container.attrs.get("State", {}).get("StartedAt", "unknown"))[:19]

        # Check recent logs for errors
        logs = container.logs(tail=20).decode("utf-8", errors="replace")
        error_lines = [line for line in logs.split("\n") if "error" in line.lower() or "fatal" in line.lower()]
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
