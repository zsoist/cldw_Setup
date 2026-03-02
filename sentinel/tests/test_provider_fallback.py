"""Provider fallback tests for SentinelAgent."""

from unittest.mock import MagicMock, patch

import pytest

from config import SentinelConfig
from sentinel import SentinelAgent


def _google_text_response(text: str) -> MagicMock:
    part = MagicMock()
    part.text = text
    part.function_call = None

    content = MagicMock()
    content.role = "model"
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _google_empty_response() -> MagicMock:
    content = MagicMock()
    content.role = "model"
    content.parts = []

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _build_config(tmp_path) -> SentinelConfig:
    return SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="anthropic",
        anthropic_api_key="anthropic-key",
        google_api_key="google-key",
        model="claude-sonnet-4-6",
        log_file=str(tmp_path / "sentinel.log"),
        audit_log_file=str(tmp_path / "audit.log"),
    )


def _build_google_primary_config(tmp_path) -> SentinelConfig:
    return SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="google",
        anthropic_api_key="anthropic-key",
        google_api_key="google-key",
        model="gemini-2.5-flash",
        log_file=str(tmp_path / "sentinel.log"),
        audit_log_file=str(tmp_path / "audit.log"),
    )


def test_no_auto_fallback_on_anthropic_auth_failure(tmp_path):
    """Auto-fallback is disabled. When Anthropic fails, return error — don't switch to Google."""
    config = _build_config(tmp_path)

    with patch("sentinel.Anthropic") as mock_anthropic, patch(
        "sentinel.SentinelAgent._init_google_client"
    ) as mock_google_init:
        anthropic_client = MagicMock()
        anthropic_client.messages.create.side_effect = RuntimeError("invalid x-api-key")
        mock_anthropic.return_value = anthropic_client

        google_model = MagicMock()
        google_model.generate_content.return_value = _google_text_response("fallback ok")
        mock_google_init.return_value = (MagicMock(), google_model)

        agent = SentinelAgent(config)
        result = agent.process_message(12345, "check disk usage on /var")

        assert "temporarily unavailable" in result.lower() or "retry" in result.lower()
        assert anthropic_client.messages.create.call_count >= 1
        # Auto-fallback disabled: Google should NOT be called
        assert google_model.generate_content.call_count == 0


def test_repeated_failures_return_error_without_fallback(tmp_path):
    """Auto-fallback disabled. Repeated provider failures return error each time — no Google fallback."""
    config = _build_config(tmp_path)

    with patch("sentinel.Anthropic") as mock_anthropic, patch(
        "sentinel.SentinelAgent._init_google_client"
    ) as mock_google_init:
        anthropic_client = MagicMock()
        anthropic_client.messages.create.side_effect = RuntimeError("invalid x-api-key")
        mock_anthropic.return_value = anthropic_client

        google_model = MagicMock()
        google_model.generate_content.return_value = _google_text_response("fallback ok")
        mock_google_init.return_value = (MagicMock(), google_model)

        agent = SentinelAgent(config)
        result1 = agent.process_message(12345, "check disk usage round one")
        assert "temporarily unavailable" in result1.lower() or "retry" in result1.lower()

        result2 = agent.process_message(12345, "check disk usage round two")
        assert "temporarily unavailable" in result2.lower() or "retry" in result2.lower()

        # Auto-fallback disabled: Google should NEVER be called
        assert google_model.generate_content.call_count == 0


def test_provider_failure_does_not_persist_orphan_user_turn(tmp_path):
    """When provider fails, the user turn should not persist in conversation history."""
    config = _build_config(tmp_path)

    with patch("sentinel.Anthropic") as mock_anthropic, patch(
        "sentinel.SentinelAgent._init_google_client"
    ) as mock_google_init:
        anthropic_client = MagicMock()
        anthropic_client.messages.create.side_effect = RuntimeError("invalid x-api-key")
        mock_anthropic.return_value = anthropic_client

        google_model = MagicMock()
        google_model.generate_content.return_value = _google_text_response("fallback ok")
        mock_google_init.return_value = (MagicMock(), google_model)

        agent = SentinelAgent(config)
        result = agent.process_message(12345, "check disk usage on /var")

        assert "temporarily unavailable" in result.lower() or "retry" in result.lower()
        assert agent.conversations.get(12345, []) == []


def test_non_recoverable_primary_error_does_not_fallback(tmp_path):
    config = _build_config(tmp_path)

    with patch("sentinel.Anthropic") as mock_anthropic, patch(
        "sentinel.SentinelAgent._init_google_client"
    ) as mock_google_init:
        anthropic_client = MagicMock()
        anthropic_client.messages.create.side_effect = RuntimeError("unexpected parser state")
        mock_anthropic.return_value = anthropic_client

        google_model = MagicMock()
        google_model.generate_content.return_value = _google_text_response("fallback ok")
        mock_google_init.return_value = (MagicMock(), google_model)

        agent = SentinelAgent(config)
        with pytest.raises(RuntimeError, match="unexpected parser state"):
            agent.process_message(12345, "check disk usage on /var")

        assert google_model.generate_content.call_count == 0


def test_google_empty_response_does_not_fallback_to_anthropic(tmp_path):
    config = _build_google_primary_config(tmp_path)

    with patch("sentinel.Anthropic") as mock_anthropic, patch(
        "sentinel.SentinelAgent._init_google_client"
    ) as mock_google_init:
        anthropic_client = MagicMock()
        mock_anthropic.return_value = anthropic_client

        anthropic_response = MagicMock()
        anthropic_response.stop_reason = "end_turn"
        anthropic_text_block = MagicMock()
        anthropic_text_block.type = "text"
        anthropic_text_block.text = "anthropic fallback ok"
        anthropic_response.content = [anthropic_text_block]
        anthropic_client.messages.create.return_value = anthropic_response

        google_model = MagicMock()
        google_model.generate_content.side_effect = [
            _google_empty_response(),
            _google_empty_response(),
        ]
        mock_google_init.return_value = (MagicMock(), google_model)

        agent = SentinelAgent(config)
        result = agent.process_message(12345, "check disk usage on /var")

        assert "empty response" in result.lower()
        assert google_model.generate_content.call_count >= 2
        assert anthropic_client.messages.create.call_count == 0


def test_google_empty_response_without_fallback_returns_retry_message(tmp_path):
    config = SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="google",
        anthropic_api_key="",
        google_api_key="google-key",
        model="gemini-2.5-flash",
        log_file=str(tmp_path / "sentinel.log"),
        audit_log_file=str(tmp_path / "audit.log"),
    )

    with patch("sentinel.SentinelAgent._init_google_client") as mock_google_init:
        google_model = MagicMock()
        google_model.generate_content.side_effect = [
            _google_empty_response(),
            _google_empty_response(),
        ]
        mock_google_init.return_value = (MagicMock(), google_model)

        agent = SentinelAgent(config)
        result = agent.process_message(12345, "check disk usage on /var")

        assert "empty response" in result.lower()
        assert google_model.generate_content.call_count >= 2
