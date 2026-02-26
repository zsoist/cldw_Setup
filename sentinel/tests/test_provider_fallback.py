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
        model="claude-haiku-4-5",
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


def test_falls_back_to_google_on_anthropic_auth_failure(tmp_path):
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
        result = agent.process_message(12345, "status")

        assert result == "fallback ok"
        assert anthropic_client.messages.create.call_count == 1
        assert google_model.generate_content.call_count == 1


def test_backoff_skips_primary_provider_after_failure(tmp_path):
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
        assert agent.process_message(12345, "status one") == "fallback ok"

        anthropic_calls_after_first = anthropic_client.messages.create.call_count
        assert anthropic_calls_after_first == 1

        assert agent.process_message(12345, "status two") == "fallback ok"
        assert anthropic_client.messages.create.call_count == anthropic_calls_after_first
        assert google_model.generate_content.call_count == 2


def test_recoverable_primary_failure_does_not_persist_orphan_user_turn(tmp_path):
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
        result = agent.process_message(12345, "status")

        assert result == "fallback ok"
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
            agent.process_message(12345, "status")

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
        result = agent.process_message(12345, "status")

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
        result = agent.process_message(12345, "status")

        assert "empty response" in result.lower()
        assert google_model.generate_content.call_count >= 2
