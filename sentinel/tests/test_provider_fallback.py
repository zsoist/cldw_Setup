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
