"""Tests for tool definitions and execution."""
import json
import pytest
from unittest.mock import patch, MagicMock
from tools import (
    GOOGLE_TOOLS,
    TOOLS,
    execute_tool,
    is_command_allowed,
    _read_gateway_internal_log,
    _estimate_docker_service_cost,
    execute_manage_cron,
    _BRAVE_COST_PER_QUERY,
    _MODEL_COST_PER_M,
)


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
        assert len(TOOLS) == 12

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
        mock_container.stats.return_value = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200000},
                "system_cpu_usage": 1000000,
                "online_cpus": 3,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100000},
                "system_cpu_usage": 500000,
            },
            "memory_stats": {
                "usage": 256 * 1024 * 1024,
                "limit": 4096 * 1024 * 1024,
            },
        }
        mock_docker.return_value.containers.get.return_value = mock_container

        result = execute_tool("docker_status", {})
        assert "containers" in result
        c = result["containers"][0]
        assert c["name"] == "openclaw-gateway"
        assert c["status"] == "running"
        assert "cpu_percent" in c
        assert c["memory_mb"] == 256.0
        assert c["memory_limit_mb"] == 4096

    @patch("tools.docker.from_env")
    def test_docker_status_exited_container_no_stats(self, mock_docker):
        mock_container = MagicMock()
        mock_container.name = "openclaw-gateway"
        mock_container.status = "exited"
        mock_container.image.tags = ["openclaw:latest"]
        mock_container.attrs = {"Created": "2026-02-18T10:00:00"}
        mock_docker.return_value.containers.get.return_value = mock_container

        result = execute_tool("docker_status", {})
        c = result["containers"][0]
        assert c["status"] == "exited"
        assert "cpu_percent" not in c
        assert "memory_mb" not in c

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
        # HTTP probe: exec_run inside container returns "200"
        mock_container.exec_run.return_value = MagicMock(output=(b"200", b""))
        mock_docker.return_value.containers.get.return_value = mock_container
        result = execute_tool("check_openclaw_health", {})

        assert result["status"] == "running"
        assert result["docker_health"] == "healthy"
        assert result["gateway_ready"] is True
        assert result["http_probe_status"] == "200"


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


def _make_log_entry(msg: str, ts: str = "2026-03-01T12:00:00.000Z", level: str = "DEBUG") -> str:
    """Build a JSON log line matching OpenClaw gateway internal format."""
    return json.dumps({
        "0": '{"subsystem":"agent/embedded"}',
        "1": msg,
        "_meta": {"logLevelName": level},
        "time": ts,
    })


class TestReadGatewayInternalLog:
    """Test the shared gateway internal log reader."""

    def test_parses_json_entries(self):
        log_data = "\n".join([
            _make_log_entry("embedded run start: runId=abc model=gpt-5.3-codex", "2026-03-01T11:00:00.000Z"),
            _make_log_entry("embedded run done: runId=abc durationMs=5000 aborted=false", "2026-03-01T11:00:05.000Z"),
        ])
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(
            exit_code=0,
            output=(log_data.encode("utf-8"), None),
        )
        # _read_gateway_internal_log uses "import datetime as _dt" internally,
        # so we cannot mock it at module level. Instead, use a real datetime
        # with test data whose timestamps fall within the time window.
        # With large since_hours, it reads today + yesterday (both hit the mock),
        # so entries are doubled.
        entries = _read_gateway_internal_log(mock_container, since_hours=87600)

        assert len(entries) >= 2  # May be doubled from multi-day reads
        assert any("embedded run start" in e["msg"] for e in entries)
        assert entries[0]["level"] == "DEBUG"

    def test_handles_exec_failure(self):
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(
            exit_code=1, output=(None, b"not found"),
        )
        entries = _read_gateway_internal_log(mock_container, since_hours=1)
        assert entries == []

    def test_skips_malformed_json(self):
        log_data = "\n".join([
            "not json at all",
            _make_log_entry("valid entry", "2026-03-01T11:00:00.000Z"),
            "{bad json",
        ])
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(
            exit_code=0,
            output=(log_data.encode("utf-8"), None),
        )
        entries = _read_gateway_internal_log(mock_container, since_hours=87600)
        assert len(entries) >= 1
        assert all("valid entry" in e["msg"] for e in entries)


class TestCodexPricing:
    """Test that Codex model is correctly priced at $0."""

    def test_codex_in_model_cost_map(self):
        assert "gpt-5.3-codex" in _MODEL_COST_PER_M
        assert _MODEL_COST_PER_M["gpt-5.3-codex"]["input"] == 0.0
        assert _MODEL_COST_PER_M["gpt-5.3-codex"]["output"] == 0.0

    def test_codex_runs_cost_zero(self):
        parsed = {
            "runs": 10,
            "models": {"gpt-5.3-codex": 10},
            "errors": 0,
            "brave_calls": 0,
            "status": "running",
            "started_at": "2026-03-01T10:00",
        }
        result = _estimate_docker_service_cost(parsed)
        assert result["est_usd"] == 0.0
        assert result["by_model"]["gpt-5.3-codex"]["est_usd"] == 0.0

    def test_flash_runs_cost_nonzero(self):
        parsed = {
            "runs": 10,
            "models": {"gemini-2.5-flash": 10},
            "errors": 0,
            "brave_calls": 0,
            "status": "running",
            "started_at": "2026-03-01T10:00",
        }
        result = _estimate_docker_service_cost(parsed)
        assert result["est_usd"] > 0.0

    def test_mixed_codex_and_flash(self):
        parsed = {
            "runs": 20,
            "models": {"gpt-5.3-codex": 10, "gemini-2.5-flash": 10},
            "errors": 0,
            "brave_calls": 0,
            "status": "running",
            "started_at": "2026-03-01T10:00",
        }
        result = _estimate_docker_service_cost(parsed)
        # Cost should only come from Flash runs, not Codex
        assert result["by_model"]["gpt-5.3-codex"]["est_usd"] == 0.0
        assert result["by_model"]["gemini-2.5-flash"]["est_usd"] > 0.0


class TestBraveCostEstimation:
    """Test Brave API cost tracking."""

    def test_brave_cost_included_in_estimate(self):
        parsed = {
            "runs": 5,
            "models": {"gpt-5.3-codex": 5},
            "errors": 0,
            "brave_calls": 10,
            "status": "running",
            "started_at": "2026-03-01T10:00",
        }
        result = _estimate_docker_service_cost(parsed)
        expected_brave = round(10 * _BRAVE_COST_PER_QUERY, 6)
        assert result["brave_est_usd"] == expected_brave
        # Total should equal Brave cost (Codex runs = $0)
        assert result["est_usd"] == expected_brave

    def test_zero_brave_calls_zero_cost(self):
        parsed = {
            "runs": 1,
            "models": {"gpt-5.3-codex": 1},
            "errors": 0,
            "brave_calls": 0,
            "status": "running",
            "started_at": "2026-03-01T10:00",
        }
        result = _estimate_docker_service_cost(parsed)
        assert result["brave_est_usd"] == 0.0


class TestCheckApiSpirals:
    """Test the API spiral detection tool."""

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_healthy_gateway_returns_ok(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        mock_log_reader.return_value = [
            {"msg": "embedded run start: runId=a model=gpt-5.3-codex", "time": "2026-03-01T11:00:00Z", "level": "DEBUG"},
            {"msg": "embedded run done: runId=a durationMs=3000 aborted=false", "time": "2026-03-01T11:00:03Z", "level": "DEBUG"},
        ]
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        assert result["severity"] == "OK"

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_long_run_triggers_warning(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        mock_log_reader.return_value = [
            {"msg": "embedded run start: runId=a model=gpt-5.3-codex", "time": "2026-03-01T11:00:00Z", "level": "DEBUG"},
            {"msg": "embedded run done: runId=a durationMs=90000 aborted=false", "time": "2026-03-01T11:01:30Z", "level": "DEBUG"},
        ]
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        assert result["severity"] == "WARNING"
        assert any("90000ms" in a for a in result["alerts"])

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_critical_run_duration(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        mock_log_reader.return_value = [
            {"msg": "embedded run start: runId=a model=gpt-5.3-codex", "time": "2026-03-01T11:00:00Z", "level": "DEBUG"},
            {"msg": "embedded run done: runId=a durationMs=150000 aborted=false", "time": "2026-03-01T11:02:30Z", "level": "DEBUG"},
        ]
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        assert result["severity"] == "CRITICAL"

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_error_rate_detection(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        # 15 errors in 1 hour → error_rate = 15 > 10 → WARNING
        entries = [
            {"msg": f"error occurred {i}", "time": "2026-03-01T11:00:00Z", "level": "ERROR"}
            for i in range(15)
        ]
        mock_log_reader.return_value = entries
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        assert result["severity"] == "WARNING"
        assert any("errors/hour" in a for a in result["alerts"])

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_aborted_runs_detected(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        mock_log_reader.return_value = [
            {"msg": "embedded run start: runId=a model=gpt-5.3-codex", "time": "2026-03-01T11:00:00Z", "level": "DEBUG"},
            {"msg": "embedded run done: runId=a durationMs=5000 aborted=true", "time": "2026-03-01T11:00:05Z", "level": "DEBUG"},
        ]
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        assert result["metrics"]["gateway_logs"]["aborted_runs"] == 1
        assert any("aborted" in a for a in result["alerts"])

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_brave_cost_in_spiral_metrics(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        mock_log_reader.return_value = [
            {"msg": "brave search: query=test", "time": "2026-03-01T11:00:00Z", "level": "DEBUG"},
            {"msg": "web_search result", "time": "2026-03-01T11:00:01Z", "level": "DEBUG"},
        ]
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        assert result["metrics"]["gateway_logs"]["brave_calls"] == 2
        assert result["metrics"]["gateway_logs"]["brave_est_usd"] == round(2 * _BRAVE_COST_PER_QUERY, 6)

    @patch("tools.docker.from_env")
    @patch("tools._read_gateway_internal_log")
    def test_models_tracked_in_spiral_metrics(self, mock_log_reader, mock_docker):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "RestartCount": 0,
            "State": {"StartedAt": "2026-03-01T10:00:00Z", "Health": {"Status": "healthy"}},
        }
        mock_docker.return_value.containers.get.return_value = mock_container
        mock_log_reader.return_value = [
            {"msg": "embedded run start: runId=a model=gpt-5.3-codex", "time": "2026-03-01T11:00:00Z", "level": "DEBUG"},
            {"msg": "embedded run done: runId=a durationMs=1000 aborted=false", "time": "2026-03-01T11:00:01Z", "level": "DEBUG"},
            {"msg": "embedded run start: runId=b model=gemini-2.5-flash", "time": "2026-03-01T11:00:02Z", "level": "DEBUG"},
            {"msg": "embedded run done: runId=b durationMs=2000 aborted=false", "time": "2026-03-01T11:00:04Z", "level": "DEBUG"},
        ]
        with patch("tools.os.path.exists", return_value=False):
            result = execute_tool("check_api_spirals", {"hours": 1})
        models = result["metrics"]["gateway_logs"]["models"]
        assert models["gpt-5.3-codex"] == 1
        assert models["gemini-2.5-flash"] == 1


class TestManageCron:
    """Test cron job management across all services."""

    # --- OpenClaw cron ---

    def test_openclaw_status(self, tmp_path):
        jobs_file = tmp_path / "jobs.json"
        jobs_file.write_text(json.dumps({
            "version": 1,
            "jobs": [
                {"name": "news-brief-ai", "enabled": True},
                {"name": "news-brief-enb", "enabled": False},
            ]
        }))
        with patch("tools.open", side_effect=lambda f, *a, **kw: open(str(jobs_file), *a, **kw) if f == "/root/.openclaw/cron/jobs.json" else open(f, *a, **kw)):
            result = execute_manage_cron("openclaw", "status")
        assert len(result["jobs"]) == 2
        assert result["jobs"][0]["enabled"] is True
        assert result["jobs"][1]["enabled"] is False

    def test_openclaw_disable(self, tmp_path):
        jobs_file = tmp_path / "jobs.json"
        data = {"version": 1, "jobs": [{"name": "news-brief-ai", "enabled": True}]}
        jobs_file.write_text(json.dumps(data))

        def mock_open_fn(f, *a, **kw):
            if f == "/root/.openclaw/cron/jobs.json":
                return open(str(jobs_file), *a, **kw)
            return open(f, *a, **kw)

        with patch("tools.open", side_effect=mock_open_fn), \
             patch("tools.subprocess.run"), \
             patch("tools.docker.from_env") as mock_docker:
            mock_docker.return_value.containers.get.return_value = MagicMock()
            result = execute_manage_cron("openclaw", "disable", "news-brief-ai")

        assert result["ok"] is True
        assert result["enabled"] is False
        # Verify file was updated
        saved = json.loads(jobs_file.read_text())
        assert saved["jobs"][0]["enabled"] is False

    def test_openclaw_enable(self, tmp_path):
        jobs_file = tmp_path / "jobs.json"
        data = {"version": 1, "jobs": [{"name": "news-brief-enb", "enabled": False}]}
        jobs_file.write_text(json.dumps(data))

        def mock_open_fn(f, *a, **kw):
            if f == "/root/.openclaw/cron/jobs.json":
                return open(str(jobs_file), *a, **kw)
            return open(f, *a, **kw)

        with patch("tools.open", side_effect=mock_open_fn), \
             patch("tools.subprocess.run"), \
             patch("tools.docker.from_env") as mock_docker:
            mock_docker.return_value.containers.get.return_value = MagicMock()
            result = execute_manage_cron("openclaw", "enable", "news-brief-enb")

        assert result["ok"] is True
        assert result["enabled"] is True

    def test_openclaw_job_not_found(self, tmp_path):
        jobs_file = tmp_path / "jobs.json"
        jobs_file.write_text(json.dumps({"version": 1, "jobs": [{"name": "abc"}]}))
        with patch("tools.open", side_effect=lambda f, *a, **kw: open(str(jobs_file), *a, **kw) if f == "/root/.openclaw/cron/jobs.json" else open(f, *a, **kw)):
            result = execute_manage_cron("openclaw", "disable", "nonexistent")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_openclaw_disable_needs_job_name(self, tmp_path):
        jobs_file = tmp_path / "jobs.json"
        jobs_file.write_text(json.dumps({"version": 1, "jobs": []}))
        with patch("tools.open", side_effect=lambda f, *a, **kw: open(str(jobs_file), *a, **kw) if f == "/root/.openclaw/cron/jobs.json" else open(f, *a, **kw)):
            result = execute_manage_cron("openclaw", "disable", "")
        assert "error" in result
        assert "job_name required" in result["error"]

    # --- Job Radar ---

    @patch("urllib.request.urlopen")
    def test_jobradar_status(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"running": True, "jobs": [{"id": "cleanup", "paused": False}]}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = execute_manage_cron("jobradar", "status")
        assert result["ok"] is True

    @patch("urllib.request.urlopen")
    def test_jobradar_pause(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "message": "Paused 6 jobs"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = execute_manage_cron("jobradar", "disable")
        assert result["ok"] is True
        assert result["action"] == "disable"

    @patch("urllib.request.urlopen")
    def test_jobradar_api_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        result = execute_manage_cron("jobradar", "status")
        assert "error" in result
        assert "Job Radar API" in result["error"]

    # --- System crontab ---

    @patch("tools.subprocess.run")
    def test_system_status(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="0 3 * * * docker builder prune -f\n# comment line\n30 2 * * * /root/backup.sh\n"
        )
        result = execute_manage_cron("system", "status")
        assert result["service"] == "system"
        assert len(result["jobs"]) >= 1
        assert result["jobs"][0]["name"] == "docker-prune"
        assert result["jobs"][0]["enabled"] is True

    @patch("tools.subprocess.run")
    def test_system_disable(self, mock_run):
        mock_run.side_effect = [
            # First call: crontab -l (read)
            MagicMock(returncode=0, stdout="0 3 * * * docker builder prune -f\n30 2 * * * /root/backup.sh\n"),
            # Second call: crontab - (write)
            MagicMock(returncode=0, stderr=""),
        ]
        result = execute_manage_cron("system", "disable", "docker-prune")
        assert result["ok"] is True
        assert result["enabled"] is False
        # Verify the write call had the disabled line
        write_call = mock_run.call_args_list[1]
        new_crontab = write_call.kwargs.get("input", "")
        assert "#SENTINEL_DISABLED#" in new_crontab

    @patch("tools.subprocess.run")
    def test_system_enable(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="#SENTINEL_DISABLED# 0 3 * * * docker builder prune -f\n"),
            MagicMock(returncode=0, stderr=""),
        ]
        result = execute_manage_cron("system", "enable", "docker-prune")
        assert result["ok"] is True
        assert result["enabled"] is True
        write_call = mock_run.call_args_list[1]
        new_crontab = write_call.kwargs.get("input", "")
        assert "#SENTINEL_DISABLED#" not in new_crontab

    def test_system_unknown_job(self):
        result = execute_manage_cron("system", "disable", "nonexistent-job")
        assert "error" in result
        assert "Unknown system job" in result["error"]

    # --- Invalid service ---

    def test_invalid_service(self):
        result = execute_manage_cron("invalid", "status")
        assert "error" in result
        assert "Unknown service" in result["error"]

    # --- Tool dispatcher ---

    def test_manage_cron_in_dispatcher(self):
        """Verify manage_cron is registered in execute_tool."""
        with patch("tools.execute_manage_cron", return_value={"ok": True}) as mock:
            result = execute_tool("manage_cron", {"service": "openclaw", "action": "status"})
            mock.assert_called_once_with("openclaw", "status", "")
            assert result["ok"] is True
