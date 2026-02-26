"""Tests for API usage cost tracking."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import SentinelConfig
from cost_tracker import APICostTracker
from sentinel import SentinelAgent


def test_cost_tracker_records_daily_weekly_monthly(tmp_path):
    usage_log = tmp_path / "api-usage.jsonl"
    summary_file = tmp_path / "api-cost-summary.json"
    tracker = APICostTracker(str(usage_log), str(summary_file), retention_days=180)

    tracker.record(
        provider="google",
        model="gemini-2.5-flash",
        status="success",
        input_tokens=1000,
        output_tokens=2000,
        user_id=12345,
    )
    tracker.record(
        provider="google",
        model="gemini-2.5-flash",
        status="error",
        user_id=12345,
        error_type="RuntimeError",
        error_preview="timeout",
    )

    lines = usage_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    totals = summary["totals"]["all_time"]
    assert totals["calls"] == 2
    assert totals["success_calls"] == 1
    assert totals["error_calls"] == 1
    assert totals["usd"] > 0

    assert summary["totals"]["daily"]
    assert summary["totals"]["weekly"]
    assert summary["totals"]["monthly"]


def test_sentinel_agent_writes_usage_summary(tmp_path):
    cost_log = tmp_path / "usage.jsonl"
    cost_summary = tmp_path / "summary.json"

    config = SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="anthropic",
        anthropic_api_key="anthropic-key",
        model="claude-haiku-4-5",
        log_file=str(tmp_path / "sentinel.log"),
        audit_log_file=str(tmp_path / "audit.log"),
        api_usage_log_file=str(cost_log),
        api_cost_summary_file=str(cost_summary),
        cost_tracking_enabled=True,
    )

    with patch("sentinel.Anthropic") as mock_anthropic:
        anthropic_client = MagicMock()
        mock_anthropic.return_value = anthropic_client

        response = MagicMock()
        response.stop_reason = "end_turn"
        response.usage = {"input_tokens": 120, "output_tokens": 60}
        text_block = MagicMock()
        text_block.text = "ok"
        response.content = [text_block]
        anthropic_client.messages.create.return_value = response

        agent = SentinelAgent(config)
        result = agent.process_message(12345, "status")

    assert result == "ok"
    assert cost_log.exists()
    assert cost_summary.exists()

    summary = json.loads(cost_summary.read_text(encoding="utf-8"))
    assert summary["totals"]["all_time"]["calls"] >= 1
    assert summary["totals"]["all_time"]["usd"] > 0
