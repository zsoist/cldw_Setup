"""Tests for tool definitions and execution."""
import pytest
from unittest.mock import patch, MagicMock
from tools import GOOGLE_TOOLS, TOOLS, execute_tool, is_command_allowed


class TestCommandWhitelist:
    """Test the command whitelist/blocklist logic."""

    def test_allowed_commands(self):
        assert is_command_allowed("df -h")[0] is True
        assert is_command_allowed("free -m")[0] is True
        assert is_command_allowed("uptime")[0] is True
        assert is_command_allowed("ufw status")[0] is True
        assert is_command_allowed("docker ps --filter name=openclaw-openclaw-gateway-1")[0] is True
        assert is_command_allowed("docker stats --no-stream openclaw-openclaw-gateway-1")[0] is True
        assert is_command_allowed("journalctl -u sentinel -n 50 --no-pager")[0] is True
        assert is_command_allowed("curl -s http://127.0.0.1:18789/")[0] is True

    def test_blocked_commands(self):
        assert is_command_allowed("rm -rf /")[0] is False
        assert is_command_allowed("sudo su")[0] is False
        assert is_command_allowed("apt install something")[0] is False
        assert is_command_allowed("wget http://malicious.com")[0] is False
        assert is_command_allowed("python malicious.py")[0] is False
        assert is_command_allowed("reboot")[0] is False
        assert is_command_allowed("chmod 777 /etc/passwd")[0] is False

    def test_sensitive_file_read_commands_are_blocked(self):
        assert is_command_allowed("tail -n 200 /etc/shadow")[0] is False
        assert is_command_allowed("head -n 50 /root/.ssh/id_rsa")[0] is False
        assert is_command_allowed("wc -l /root/.openclaw/.env")[0] is False

    def test_non_local_curl_blocked(self):
        assert is_command_allowed("curl -s https://example.com")[0] is False

    def test_invalid_local_port_blocked(self):
        assert is_command_allowed("curl -s http://127.0.0.1:99999/")[0] is False

    def test_unknown_commands_blocked(self):
        assert is_command_allowed("some-random-binary")[0] is False
        assert is_command_allowed("nc -l 4444")[0] is False

    def test_command_validation_is_argument_aware(self):
        assert is_command_allowed("systemctl status openclaw")[0] is True
        assert is_command_allowed("systemctl status openclaw --no-pager")[0] is True
        assert is_command_allowed("systemctl restart openclaw")[0] is False  # restart not whitelisted
        assert is_command_allowed("systemctl status openclaw --full")[0] is False


class TestToolDefinitions:
    """Verify tool schema integrity."""

    def test_all_tools_have_required_fields(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_tool_count(self):
        assert len(TOOLS) == 9

    def test_google_function_declarations_exist(self):
        assert len(GOOGLE_TOOLS) == 1
        declarations = GOOGLE_TOOLS[0]["function_declarations"]
        assert len(declarations) == len(TOOLS)
        assert declarations[0]["name"] == TOOLS[0]["name"]


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
        mock_docker.return_value.containers.get.return_value = mock_container

        result = execute_tool("docker_status", {})
        assert "containers" in result
        assert result["containers"][0]["name"] == "openclaw-gateway"
        assert result["containers"][0]["status"] == "running"

    @patch("tools.docker.from_env")
    def test_docker_restart(self, mock_docker):
        mock_container = MagicMock()
        mock_docker.return_value.containers.get.return_value = mock_container

        result = execute_tool("docker_restart", {"container_name": "openclaw-openclaw-gateway-1"})
        assert result["status"] == "restarted"
        mock_container.restart.assert_called_once_with(timeout=30)

    def test_docker_restart_disallowed_container(self):
        result = execute_tool("docker_restart", {"container_name": "postgres"})
        assert "allowlist" in result["error"]

    @patch("tools.docker.from_env")
    def test_docker_logs_consistent_shape(self, mock_docker):
        mock_container = MagicMock()
        mock_container.logs.return_value = b"log line"
        mock_docker.return_value.containers.get.return_value = mock_container
        result = execute_tool("docker_logs", {"container_name": "openclaw-openclaw-gateway-1", "lines": 5})
        assert result["container"] == "openclaw-openclaw-gateway-1"
        assert result["lines"] == 5
        assert "log line" in result["logs"]

    @patch("tools.docker.from_env")
    def test_openclaw_health_uses_docker_health(self, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "State": {
                "StartedAt": "2026-02-21T21:08:56.392Z",
                "Health": {"Status": "healthy"},
            }
        }
        mock_container.logs.return_value = b"gateway started\nno errors"
        mock_docker.return_value.containers.get.return_value = mock_container
        with patch("tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="200", returncode=0)
            result = execute_tool("check_openclaw_health", {})

        assert result["status"] == "running"
        assert result["docker_health"] == "healthy"
        assert result["gateway_ready"] is True
        assert result["http_fallback_status"] == "200"


class TestRunCommand:
    """Test the run_command tool with whitelist enforcement."""

    @patch("tools.subprocess.run")
    def test_allowed_command_executes(self, mock_run):
        mock_run.return_value = MagicMock(stdout="output", stderr="", returncode=0)
        result = execute_tool("run_command", {"command": "df -h"})
        assert result["returncode"] == 0
        assert result["stdout"] == "output"

    def test_blocked_command_rejected(self):
        result = execute_tool("run_command", {"command": "rm -rf /"})
        assert "error" in result
        assert "blocked" in result["error"].lower() or "Blocked" in result["error"]

    def test_unknown_command_rejected(self):
        result = execute_tool("run_command", {"command": "nc -l 4444"})
        assert "error" in result


class TestUnknownTool:
    """Test dispatcher behavior for unknown tools."""

    def test_unknown_tool_returns_error(self):
        result = execute_tool("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]
