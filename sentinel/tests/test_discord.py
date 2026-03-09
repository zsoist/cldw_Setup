"""Tests for the Sentinel Discord bot handler.

All tests are fully mocked — zero API cost, zero network calls.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the sentinel package root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> MagicMock:
    """Build a mock SentinelConfig with sensible defaults."""
    cfg = MagicMock()
    cfg.allowed_discord_user_ids = overrides.get("allowed_discord_user_ids", [111, 222])
    cfg.usd_to_cop_rate = overrides.get("usd_to_cop_rate", 4000.0)
    cfg.discord_token = overrides.get("discord_token", "fake-discord-token")
    cfg.discord_guild_id = overrides.get("discord_guild_id", 0)
    cfg.discord_channel_id = overrides.get("discord_channel_id", 0)
    cfg.provider = overrides.get("provider", "openai")
    cfg.model = overrides.get("model", "gpt-5-codex")
    return cfg


def _make_agent() -> MagicMock:
    """Build a mock SentinelAgent with request-stats helpers."""
    agent = MagicMock()

    def _new_request_stats() -> dict[str, Any]:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_usd": 0.0,
            "calls": 0,
            "error_calls": 0,
            "providers": [],
            "models": [],
            "brave_api_calls": 0,
            "status": "started",
        }

    agent._new_request_stats = _new_request_stats

    _stats_store: dict[int, dict] = {}

    def _store(uid: int, stats: dict) -> None:
        _stats_store[uid] = dict(stats)

    def _get(uid: int) -> dict:
        return dict(_stats_store.get(uid, _new_request_stats()))

    agent._store_last_request_stats = MagicMock(side_effect=_store)
    agent.get_last_request_stats = MagicMock(side_effect=_get)
    agent._stats_store = _stats_store  # expose for test inspection

    return agent


@pytest.fixture
def config():
    return _make_config()


@pytest.fixture
def agent():
    return _make_agent()


@pytest.fixture
def bot(config, agent):
    """Create a SentinelDiscordBot with mocked discord.Client + CommandTree."""
    with patch("discord_handler.discord.Client"), \
         patch("discord_handler.discord.Intents"), \
         patch("discord_handler.app_commands.CommandTree"):
        from discord_handler import SentinelDiscordBot
        return SentinelDiscordBot(config, agent)


# ---------------------------------------------------------------------------
# 1. _is_authorized
# ---------------------------------------------------------------------------

class TestIsAuthorized:

    def test_authorized_user(self, bot):
        assert bot._is_authorized(111) is True

    def test_authorized_second_user(self, bot):
        assert bot._is_authorized(222) is True

    def test_unauthorized_user(self, bot):
        assert bot._is_authorized(999) is False

    def test_unauthorized_zero(self, bot):
        assert bot._is_authorized(0) is False


# ---------------------------------------------------------------------------
# 1b. _is_sentinel_channel
# ---------------------------------------------------------------------------

class TestIsSentinelChannel:

    def test_no_restriction_configured(self, bot):
        """When discord_channel_id is 0, all channels are allowed."""
        bot.config.discord_channel_id = 0
        assert bot._is_sentinel_channel(12345) is True
        assert bot._is_sentinel_channel(99999) is True

    def test_matching_channel(self, bot):
        bot.config.discord_channel_id = 1477876418590408795
        assert bot._is_sentinel_channel(1477876418590408795) is True

    def test_non_matching_channel(self, bot):
        bot.config.discord_channel_id = 1477876418590408795
        assert bot._is_sentinel_channel(1477876150977167380) is False

    def test_zero_channel_id_always_allows(self):
        """Explicit zero = no restriction."""
        cfg = _make_config(discord_channel_id=0)
        agent = _make_agent()
        with patch("discord_handler.discord.Client"), \
             patch("discord_handler.discord.Intents"), \
             patch("discord_handler.app_commands.CommandTree"):
            from discord_handler import SentinelDiscordBot
            b = SentinelDiscordBot(cfg, agent)
        assert b._is_sentinel_channel(999) is True


# ---------------------------------------------------------------------------
# 2. _check_static_response
# ---------------------------------------------------------------------------

class TestCheckStaticResponse:

    @pytest.mark.parametrize("text,expected", [
        ("hi", "Sentinel online."),
        ("hello", "Sentinel online."),
        ("Hi", "Sentinel online."),
        ("HELLO", "Sentinel online."),
        ("thanks", "No problem."),
        ("ok", "Acknowledged."),
        ("ping", "Pong."),
        ("model", "Sentinel runs on gpt-5-codex via OpenAI."),
        ("codex", "OpenClaw uses GPT-5.3 Codex (subscription-covered). Sentinel uses gpt-5-codex via OpenAI."),
    ])
    def test_known_keywords(self, bot, text, expected):
        assert bot._check_static_response(text) == expected

    def test_help_response(self, bot):
        resp = bot._check_static_response("help")
        assert resp is not None
        assert "/status" in resp
        assert "/cost" in resp

    def test_capabilities_response(self, bot):
        resp = bot._check_static_response("capabilities")
        assert resp is not None
        assert "System monitoring" in resp
        assert "Docker container" in resp

    def test_what_can_you_do(self, bot):
        resp = bot._check_static_response("what can you do")
        assert resp is not None
        assert "Capabilities" in resp

    def test_unknown_text_returns_none(self, bot):
        assert bot._check_static_response("reboot the server") is None

    def test_unknown_random_text(self, bot):
        assert bot._check_static_response("something completely different") is None

    def test_empty_string(self, bot):
        assert bot._check_static_response("") is None

    def test_case_insensitive(self, bot):
        assert bot._check_static_response("PING") == "Pong."
        assert bot._check_static_response("Help") is not None


# ---------------------------------------------------------------------------
# 3. _build_usage_footer
# ---------------------------------------------------------------------------

class TestBuildUsageFooter:

    def test_zero_cost_footer(self, bot):
        # Prime zero stats
        bot._set_zero_cost_stats(111)
        footer = bot._build_usage_footer(111)
        assert "Tokens used: 0/0" in footer
        assert "USD $0.000000" in footer
        assert "COP $0.00" in footer
        assert "Brave" not in footer

    def test_footer_with_tokens(self, bot):
        bot.agent._stats_store[111] = {
            "input_tokens": 500,
            "output_tokens": 200,
            "estimated_usd": 0.001,
            "brave_api_calls": 0,
        }
        footer = bot._build_usage_footer(111)
        assert "500/200" in footer
        assert "USD $0.001000" in footer
        # COP = 0.001 * 4000 = 4.0
        assert "COP $4.00" in footer
        assert "Brave" not in footer

    def test_footer_with_brave_calls(self, bot):
        bot.agent._stats_store[111] = {
            "input_tokens": 100,
            "output_tokens": 50,
            "estimated_usd": 0.0005,
            "brave_api_calls": 3,
        }
        footer = bot._build_usage_footer(111)
        assert "Brave api: 3" in footer

    def test_footer_no_brave_when_zero(self, bot):
        bot.agent._stats_store[111] = {
            "input_tokens": 10,
            "output_tokens": 5,
            "estimated_usd": 0.0,
            "brave_api_calls": 0,
        }
        footer = bot._build_usage_footer(111)
        assert "Brave" not in footer


# ---------------------------------------------------------------------------
# 4. _reply_chunked
# ---------------------------------------------------------------------------

class TestReplyChunked:

    @pytest.mark.asyncio
    async def test_short_text_single_message(self, bot):
        """Text under 1900 chars should be sent as a single message."""
        target = MagicMock()
        target.channel = MagicMock()
        target.channel.send = AsyncMock()

        # Not a discord.Interaction → goes to target.channel.send
        with patch("discord_handler.isinstance", return_value=False):
            await bot._reply_chunked(target, "Hello world")

        target.channel.send.assert_awaited_once()
        sent_text = target.channel.send.call_args[0][0]
        assert "Hello world" in sent_text

    @pytest.mark.asyncio
    async def test_long_text_gets_chunked(self, bot):
        """Text over 1900 chars should be split into multiple messages."""
        long_text = "\n".join([f"Line {i}: " + "x" * 80 for i in range(50)])
        assert len(long_text) > 1900

        target = MagicMock()
        target.channel = MagicMock()
        target.channel.send = AsyncMock()

        with patch("discord_handler.isinstance", return_value=False):
            await bot._reply_chunked(target, long_text)

        call_count = target.channel.send.await_count
        assert call_count >= 2
        # Verify chunk headers
        first_text = target.channel.send.call_args_list[0][0][0]
        assert first_text.startswith("[1/")

    @pytest.mark.asyncio
    async def test_empty_text_fallback(self, bot):
        """Empty text should produce '(empty response)'."""
        target = MagicMock()
        target.channel = MagicMock()
        target.channel.send = AsyncMock()

        with patch("discord_handler.isinstance", return_value=False):
            await bot._reply_chunked(target, "")

        target.channel.send.assert_awaited_once()
        sent = target.channel.send.call_args[0][0]
        assert "(empty response)" in sent

    @pytest.mark.asyncio
    async def test_very_long_single_line_gets_force_split(self, bot):
        """A single line over 1900 chars must be force-split."""
        line = "A" * 4000
        target = MagicMock()
        target.channel = MagicMock()
        target.channel.send = AsyncMock()

        with patch("discord_handler.isinstance", return_value=False):
            await bot._reply_chunked(target, line)

        assert target.channel.send.await_count >= 2


# ---------------------------------------------------------------------------
# 5. _format_static_stats
# ---------------------------------------------------------------------------

class TestFormatStaticStats:

    @patch("discord_handler.execute_docker_status")
    @patch("discord_handler.execute_system_stats")
    def test_format_includes_system_info(self, mock_sys, mock_docker, bot):
        mock_sys.return_value = {
            "cpu_percent": 12.5,
            "memory_used_gb": 1.5,
            "memory_total_gb": 4.0,
            "memory_percent": 37.5,
            "disk_used_gb": 15.0,
            "disk_total_gb": 40.0,
            "disk_percent": 37.5,
            "swap_used_gb": 0.0,
            "swap_total_gb": 2.0,
            "uptime": "5 days, 3:22:10",
        }
        mock_docker.return_value = {
            "containers": [
                {
                    "name": "openclaw-gateway",
                    "status": "running",
                    "cpu_percent": 2.3,
                    "memory_mb": 350,
                    "memory_limit_mb": 1024,
                },
                {
                    "name": "job-radar-agent",
                    "status": "running",
                    "cpu_percent": 0.5,
                    "memory_mb": 120,
                    "memory_limit_mb": 512,
                },
            ]
        }

        result = bot._format_static_stats(111)

        assert "**System Status**" in result
        assert "CPU: 12.5%" in result
        assert "RAM: 1.5/4.0GB" in result
        assert "Disk: 15.0/40.0GB" in result
        assert "Swap: 0.0/2.0GB" in result
        assert "Uptime: 5 days" in result
        assert "**Containers:**" in result
        assert "openclaw-gateway" in result
        assert "running" in result
        assert "CPU 2.3%" in result
        assert "RAM 350/1024MB" in result
        assert "job-radar-agent" in result

    @patch("discord_handler.execute_docker_status")
    @patch("discord_handler.execute_system_stats")
    def test_container_without_cpu_info(self, mock_sys, mock_docker, bot):
        """Containers without cpu/mem should still appear."""
        mock_sys.return_value = {
            "cpu_percent": 5, "memory_used_gb": 1, "memory_total_gb": 4,
            "memory_percent": 25, "disk_used_gb": 10, "disk_total_gb": 40,
            "disk_percent": 25, "swap_used_gb": 0, "swap_total_gb": 1,
            "uptime": "1 day",
        }
        mock_docker.return_value = {
            "containers": [
                {"name": "some-container", "status": "exited"},
            ]
        }

        result = bot._format_static_stats(111)
        assert "some-container: exited" in result
        # No CPU/RAM line
        assert "CPU" not in result.split("some-container")[1]

    @patch("discord_handler.execute_docker_status")
    @patch("discord_handler.execute_system_stats")
    def test_sets_zero_cost_stats(self, mock_sys, mock_docker, bot):
        """_format_static_stats should call _set_zero_cost_stats."""
        mock_sys.return_value = {
            "cpu_percent": 0, "memory_used_gb": 0, "memory_total_gb": 0,
            "memory_percent": 0, "disk_used_gb": 0, "disk_total_gb": 0,
            "disk_percent": 0, "swap_used_gb": 0, "swap_total_gb": 0,
            "uptime": "0",
        }
        mock_docker.return_value = {"containers": []}

        bot._format_static_stats(111)
        # Verify zero-cost stats were stored
        stored = bot.agent._stats_store.get(111)
        assert stored is not None
        assert stored["status"] == "cached"


# ---------------------------------------------------------------------------
# 6. _format_cost_dashboard
# ---------------------------------------------------------------------------

class TestFormatCostDashboard:

    def test_full_dashboard(self):
        """Test with a complete result dict."""
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {
                "sentinel": {
                    "usd": 0.0012,
                    "input_tokens": 5000,
                    "output_tokens": 1500,
                    "calls": 10,
                    "errors": 1,
                    "brave_calls": 2,
                    "is_estimate": False,
                },
                "openclaw": {
                    "est_usd": 0.005,
                    "est_input_tokens": 20000,
                    "est_output_tokens": 8000,
                    "runs": 5,
                    "errors": 0,
                    "brave_calls": 4,
                    "is_estimate": True,
                    "status": "running",
                },
                "job_radar": {
                    "est_usd": 0.001,
                    "est_input_tokens": 3000,
                    "est_output_tokens": 500,
                    "runs": 2,
                    "errors": 0,
                    "brave_calls": 0,
                    "is_estimate": True,
                    "status": "running",
                },
            },
            "total": {
                "usd": 0.0072,
                "cop": 28.8,
                "total_runs": 17,
                "has_estimates": True,
                "daily_budget_remaining": 4.9928,
                "budget_pct_used": 0.144,
            },
        }

        dashboard = SentinelDiscordBot._format_cost_dashboard(result)

        assert "Today" in dashboard
        assert "Sentinel" in dashboard
        assert "OpenClaw Gateway" in dashboard
        assert "Job Radar" in dashboard
        assert "[OK]" in dashboard
        assert "TOTAL:" in dashboard
        assert "$0.0072" in dashboard
        assert "API calls: 17" in dashboard
        assert "Budget:" in dashboard
        assert "Remaining:" in dashboard
        assert "(~) = estimated" in dashboard

    def test_period_label_all(self):
        from discord_handler import SentinelDiscordBot

        result = {"period": "all", "services": {}, "total": {}}
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "All Time" in dashboard

    def test_period_label_week(self):
        from discord_handler import SentinelDiscordBot

        result = {"period": "week", "services": {}, "total": {}}
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "This Week" in dashboard

    def test_period_label_month(self):
        from discord_handler import SentinelDiscordBot

        result = {"period": "month", "services": {}, "total": {}}
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "This Month" in dashboard

    def test_service_with_error(self):
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {
                "sentinel": {"error": "log file not found"},
            },
            "total": {},
        }
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "log file not found" in dashboard

    def test_service_with_by_model(self):
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {
                "sentinel": {
                    "usd": 0.002,
                    "input_tokens": 5000,
                    "output_tokens": 1000,
                    "calls": 8,
                    "errors": 0,
                    "brave_calls": 0,
                    "is_estimate": False,
                    "by_model": {
                        "gemini-2.5-flash": {"calls": 6, "usd": 0.0015},
                        "haiku": {"calls": 2, "usd": 0.0005},
                    },
                },
            },
            "total": {},
        }
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "gemini-2.5-flash" in dashboard
        assert "haiku" in dashboard
        assert "6 calls" in dashboard

    def test_tokens_formatted_as_k(self):
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {
                "sentinel": {
                    "usd": 0.01,
                    "input_tokens": 15000,
                    "output_tokens": 3000,
                    "calls": 5,
                    "errors": 0,
                    "brave_calls": 0,
                    "is_estimate": False,
                },
            },
            "total": {},
        }
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "15.0K in" in dashboard
        assert "3.0K out" in dashboard

    def test_small_token_counts_not_k(self):
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {
                "sentinel": {
                    "usd": 0.0001,
                    "input_tokens": 500,
                    "output_tokens": 100,
                    "calls": 1,
                    "errors": 0,
                    "brave_calls": 0,
                    "is_estimate": False,
                },
            },
            "total": {},
        }
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "500 in" in dashboard
        assert "100 out" in dashboard

    def test_budget_bar(self):
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {},
            "total": {
                "usd": 2.5,
                "cop": 10000,
                "total_runs": 100,
                "has_estimates": False,
                "daily_budget_remaining": 2.5,
                "budget_pct_used": 50.0,
            },
        }
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "Budget: [" in dashboard
        assert "##########----------" in dashboard
        assert "50.0%" in dashboard
        assert "Remaining: $2.5000 of $5.00" in dashboard

    def test_service_status_not_found(self):
        from discord_handler import SentinelDiscordBot

        result = {
            "period": "today",
            "services": {
                "openclaw": {
                    "est_usd": 0,
                    "est_input_tokens": 0,
                    "est_output_tokens": 0,
                    "runs": 0,
                    "errors": 0,
                    "brave_calls": 0,
                    "is_estimate": True,
                    "status": "not_found",
                },
            },
            "total": {},
        }
        dashboard = SentinelDiscordBot._format_cost_dashboard(result)
        assert "[DOWN]" in dashboard


# ---------------------------------------------------------------------------
# 7. _cron_to_human
# ---------------------------------------------------------------------------

class TestCronToHuman:

    def test_daily_utc(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("10 12 * * *")
        assert "Daily" in result
        assert "12:10 UTC" in result
        assert "07:10 COT" in result

    def test_daily_cot(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("0 7 * * *", "America/Bogota")
        assert "Daily" in result
        assert "07:00 COT" in result
        assert "12:00 UTC" in result

    def test_every_n_minutes(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("*/15 * * * *")
        assert "Every 15 min" in result

    def test_hourly(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("30 * * * *")
        assert "Hourly at :30" in result

    def test_multi_hour(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("0 5,17 * * *")
        assert "Daily" in result
        # Should contain both times
        assert "05:00" in result
        assert "17:00" in result

    def test_weekly_monday(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("0 3 * * 1")
        assert "Weekly Mon" in result
        assert "03:00 UTC" in result

    def test_monthly_first(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("0 0 1 * *")
        assert "Monthly (1st)" in result

    def test_short_expression_passthrough(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("bad")
        assert result == "bad"

    def test_three_fields_passthrough(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("1 2 3")
        assert result == "1 2 3"

    def test_weekly_sunday(self):
        from discord_handler import SentinelDiscordBot

        result = SentinelDiscordBot._cron_to_human("0 8 * * 0")
        assert "Weekly Sun" in result


# ---------------------------------------------------------------------------
# 8. _format_tasks
# ---------------------------------------------------------------------------

class TestFormatTasks:

    @patch("discord_handler.execute_list_scheduled_tasks")
    def test_full_task_listing(self, mock_tasks, bot):
        mock_tasks.return_value = {
            "system_crontab": {
                "jobs": [
                    "[root] 17 * * * * cd / && run-parts --report /etc/cron.hourly",
                    "[root] 25 6 * * * test -x /usr/sbin/anacron || run-parts --report /etc/cron.daily",
                    "[root] #SENTINEL_DISABLED# 0 3 * * 0 docker system prune -af",
                ]
            },
            "openclaw_cron": {
                "count": 2,
                "jobs": [
                    {
                        "name": "news-brief-ai",
                        "schedule": "10 12 * * *",
                        "tz": "UTC",
                        "enabled": True,
                        "model": "openai-codex/gpt-5.3-codex",
                        "command": "/brief ai top5",
                    },
                    {
                        "name": "news-brief-enb",
                        "schedule": "0 12 * * *",
                        "tz": "UTC",
                        "enabled": False,
                        "model": "openai-codex/gpt-5.3-codex",
                        "command": "/brief expert-networks top5",
                    },
                ],
            },
            "job_radar_scheduler": {
                "count": 2,
                "jobs": [
                    {"id": "discovery_sync", "schedule": "0 5,17 * * *", "paused": False, "desc": "Scrape new jobs"},
                    {"id": "digest_am", "schedule": "0 13 * * *", "paused": False, "desc": "Morning digest"},
                ],
            },
            "systemd_timers": {"count": 7},
        }

        result = bot._format_tasks(111)

        # Verify header
        assert "**Scheduled Tasks**" in result

        # VPS Maintenance
        assert "VPS Maintenance" in result
        assert "system-hourly" in result
        assert "system-daily" in result
        assert "docker-prune" in result
        assert "[ON]" in result
        assert "[OFF]" in result

        # OpenClaw Cron
        assert "OpenClaw Cron (2 jobs)" in result
        assert "news-brief-ai" in result
        assert "news-brief-enb" in result
        assert "gpt-5.3-codex" in result

        # Job Radar
        assert "Job Radar (2 jobs)" in result
        assert "discovery_sync" in result
        assert "digest_am" in result

        # Systemd Timers
        assert "Systemd Timers: 7 active" in result

    @patch("discord_handler.execute_list_scheduled_tasks")
    def test_empty_openclaw_jobs(self, mock_tasks, bot):
        """When no OpenClaw cron jobs exist, a note should appear."""
        mock_tasks.return_value = {
            "system_crontab": {"jobs": []},
            "openclaw_cron": {"count": 0, "jobs": [], "note": "No cron jobs configured"},
            "job_radar_scheduler": {"count": 0, "jobs": []},
            "systemd_timers": {"count": 3},
        }

        result = bot._format_tasks(111)
        assert "No cron jobs configured" in result

    @patch("discord_handler.execute_list_scheduled_tasks")
    def test_paused_job_radar_jobs(self, mock_tasks, bot):
        mock_tasks.return_value = {
            "system_crontab": {"jobs": []},
            "openclaw_cron": {"count": 0, "jobs": []},
            "job_radar_scheduler": {
                "count": 1,
                "jobs": [
                    {"id": "discovery_sync", "schedule": "0 5 * * *", "paused": True, "desc": "Scrape"},
                ],
            },
            "systemd_timers": {"count": 0},
        }

        result = bot._format_tasks(111)
        assert "[PAUSED]" in result

    @patch("discord_handler.execute_list_scheduled_tasks")
    def test_sets_zero_cost_stats(self, mock_tasks, bot):
        """_format_tasks should store zero-cost stats."""
        mock_tasks.return_value = {
            "system_crontab": {"jobs": []},
            "openclaw_cron": {"count": 0, "jobs": []},
            "job_radar_scheduler": {"count": 0, "jobs": []},
            "systemd_timers": {"count": 0},
        }

        bot._format_tasks(111)
        stored = bot.agent._stats_store.get(111)
        assert stored is not None
        assert stored["status"] == "cached"

    @patch("discord_handler.execute_list_scheduled_tasks")
    def test_cron_job_names_assigned(self, mock_tasks, bot):
        """Test the various cron command-to-name mappings."""
        mock_tasks.return_value = {
            "system_crontab": {
                "jobs": [
                    "[root] 0 2 * * * /usr/local/bin/backup-openclaw.sh",
                    "[e2scrub_all] 10 3 * * * /usr/lib/x86_64-linux-gnu/e2fsprogs/e2scrub_all_cron",
                    "[sysstat] */10 * * * * /usr/lib/sysstat/debian-sa1 1 1",
                    "[root] 47 6 * * 7 test -x /usr/sbin/anacron || run-parts --report /etc/cron.weekly",
                ]
            },
            "openclaw_cron": {"count": 0, "jobs": []},
            "job_radar_scheduler": {"count": 0, "jobs": []},
            "systemd_timers": {"count": 0},
        }

        result = bot._format_tasks(111)
        assert "openclaw-backup" in result
        assert "disk-scrub" in result
        assert "sysstat" in result
        assert "system-weekly" in result


# ---------------------------------------------------------------------------
# 9. Channel restriction on slash commands
# ---------------------------------------------------------------------------

class TestSlashCommandChannelRestriction:
    """Verify that slash commands reject usage outside the sentinel channel."""

    def _make_restricted_bot(self):
        """Create a bot with discord_channel_id set to a specific channel."""
        cfg = _make_config(
            discord_channel_id=1477876418590408795,
            discord_guild_id=1477826670760296548,
        )
        agent = _make_agent()

        # We need to capture the actual command callbacks
        registered_commands = {}

        with patch("discord_handler.discord.Client") as mock_client_cls, \
             patch("discord_handler.discord.Intents"), \
             patch("discord_handler.app_commands.CommandTree") as mock_tree_cls:

            mock_tree = MagicMock()

            def capture_command(**kwargs):
                def decorator(func):
                    registered_commands[kwargs.get("name", func.__name__)] = func
                    return func
                return decorator

            mock_tree.command = capture_command
            mock_tree_cls.return_value = mock_tree

            from discord_handler import SentinelDiscordBot
            bot = SentinelDiscordBot(cfg, agent)

        return bot, registered_commands

    def _make_interaction(self, user_id: int, channel_id: int) -> MagicMock:
        """Build a mock Interaction."""
        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.channel_id = channel_id
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.response.is_done.return_value = False
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_status_rejected_in_wrong_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876150977167380)  # #general

        await cmds["status"](interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "ephemeral" in call_args.kwargs
        assert call_args.kwargs["ephemeral"] is True
        assert "1477876418590408795" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_allowed_in_correct_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876418590408795)  # #sentinel
        interaction.channel = MagicMock()
        interaction.channel.send = AsyncMock()

        with patch("discord_handler.execute_system_stats", return_value={
            "cpu_percent": 5, "memory_used_gb": 1, "memory_total_gb": 4,
            "memory_percent": 25, "disk_used_gb": 10, "disk_total_gb": 40,
            "disk_percent": 25, "swap_used_gb": 0, "swap_total_gb": 1,
            "uptime": "1d",
        }), patch("discord_handler.execute_docker_status", return_value={"containers": []}):
            await cmds["status"](interaction)

        interaction.response.defer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cost_rejected_in_wrong_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876277753942127)  # #ai-brief

        await cmds["cost"](interaction, period="today")

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_tasks_rejected_in_wrong_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876302240288890)  # #job-radar

        await cmds["tasks"](interaction)

        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_openclaw_rejected_in_wrong_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876150977167380)

        await cmds["openclaw"](interaction)

        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_security_rejected_in_wrong_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876150977167380)

        await cmds["security"](interaction)

        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_backup_rejected_in_wrong_channel(self):
        bot, cmds = self._make_restricted_bot()
        interaction = self._make_interaction(111, 1477876150977167380)

        await cmds["backup"](interaction)

        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


# ---------------------------------------------------------------------------
# Additional: _append_usage_footer
# ---------------------------------------------------------------------------

class TestAppendUsageFooter:

    def test_appends_to_text(self, bot):
        bot._set_zero_cost_stats(111)
        result = bot._append_usage_footer(111, "some response")
        assert result.startswith("some response")
        assert "Tokens used:" in result

    def test_empty_text_returns_footer_only(self, bot):
        bot._set_zero_cost_stats(111)
        result = bot._append_usage_footer(111, "")
        assert "Tokens used:" in result
        # Should not start with newlines
        assert not result.startswith("\n")


# ---------------------------------------------------------------------------
# Additional: _set_zero_cost_stats
# ---------------------------------------------------------------------------

class TestSetZeroCostStats:

    def test_stores_cached_status(self, bot):
        bot._set_zero_cost_stats(999)
        stored = bot.agent._stats_store.get(999)
        assert stored is not None
        assert stored["status"] == "cached"
        assert stored["input_tokens"] == 0
        assert stored["output_tokens"] == 0
        assert stored["estimated_usd"] == 0.0
