"""Tests for API usage cost tracking."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import SentinelConfig
from cost_tracker import APICostTracker, _MODEL_PRICING, _PROVIDER_DEFAULT_PRICING
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
        model="claude-sonnet-4-6",
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


def test_pricing_table_matches_current_rates():
    """Verify pricing table reflects actual provider rates (Feb 2026)."""
    # Gemini 2.5 Flash: $0.30 input, $2.50 output per 1M tokens
    flash = _MODEL_PRICING["google/gemini-2.5-flash"]
    assert flash.input_per_million == 0.30
    assert flash.output_per_million == 2.50

    # Gemini 2.5 Pro: $1.25 input, $10.00 output per 1M tokens
    pro = _MODEL_PRICING["google/gemini-2.5-pro"]
    assert pro.input_per_million == 1.25
    assert pro.output_per_million == 10.00

    # Claude Haiku 4.5: $1.00 input, $5.00 output per 1M tokens
    haiku = _MODEL_PRICING["anthropic/claude-haiku-4-5"]
    assert haiku.input_per_million == 1.00
    assert haiku.output_per_million == 5.00

    # Claude Sonnet 4.6: $3.00 input, $15.00 output per 1M tokens
    sonnet = _MODEL_PRICING["anthropic/claude-sonnet-4-6"]
    assert sonnet.input_per_million == 3.00
    assert sonnet.output_per_million == 15.00

    # Claude Opus 4.6: $5.00 input, $25.00 output per 1M tokens
    opus = _MODEL_PRICING["anthropic/claude-opus-4-6"]
    assert opus.input_per_million == 5.00
    assert opus.output_per_million == 25.00

    # Provider defaults match primary model in each tier
    assert _PROVIDER_DEFAULT_PRICING["google"].input_per_million == 0.30
    assert _PROVIDER_DEFAULT_PRICING["google"].output_per_million == 2.50
    # Anthropic default = Sonnet 4.6 (Haiku is banned from production use)
    assert _PROVIDER_DEFAULT_PRICING["anthropic"].input_per_million == 3.00
    assert _PROVIDER_DEFAULT_PRICING["anthropic"].output_per_million == 15.00


def test_pruning_throttled_to_interval(tmp_path):
    """Pruning should not run on every record() call."""
    usage_log = tmp_path / "api-usage.jsonl"
    summary_file = tmp_path / "api-cost-summary.json"
    tracker = APICostTracker(str(usage_log), str(summary_file), retention_days=180)

    for _ in range(10):
        tracker.record(
            provider="google",
            model="gemini-2.5-flash",
            status="success",
            input_tokens=100,
            output_tokens=50,
            user_id=12345,
        )

    # Counter should be 10 (below 100 threshold), no prune executed
    assert tracker._records_since_prune == 10


def test_stale_user_cleanup(tmp_path):
    """Stale user dict entries are cleaned up after 2x conversation TTL."""
    config = SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345, 67890],
        provider="anthropic",
        anthropic_api_key="anthropic-key",
        model="claude-sonnet-4-6",
        log_file=str(tmp_path / "sentinel.log"),
        audit_log_file=str(tmp_path / "audit.log"),
        conversation_ttl_seconds=60,
    )

    with patch("sentinel.Anthropic") as mock_anthropic:
        anthropic_client = MagicMock()
        mock_anthropic.return_value = anthropic_client

        response = MagicMock()
        response.stop_reason = "end_turn"
        response.usage = {"input_tokens": 10, "output_tokens": 5}
        text_block = MagicMock()
        text_block.text = "ok"
        response.content = [text_block]
        anthropic_client.messages.create.return_value = response

        agent = SentinelAgent(config)

        # Simulate user activity
        agent.process_message(12345, "test")
        assert 12345 in agent._last_activity

        # Simulate time passing beyond 2x TTL (120s for TTL=60)
        agent._last_activity[12345] = time.monotonic() - 130

        # Next request from different user triggers cleanup
        agent.process_message(67890, "test")

        # User 12345 should be cleaned up
        assert 12345 not in agent._last_activity
        assert 12345 not in agent.conversations
        assert 12345 not in agent._request_windows
        assert 12345 not in agent._last_request_stats
