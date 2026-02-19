"""Shared test fixtures."""
import pytest
from unittest.mock import MagicMock, patch
from config import SentinelConfig


@pytest.fixture
def mock_config():
    """Config with test values."""
    return SentinelConfig(
        telegram_token="test-token-123",
        allowed_user_ids=[12345],
        anthropic_api_key="test-api-key",
        model="claude-haiku-4-5",
    )


@pytest.fixture
def mock_anthropic_client():
    """Mocked Anthropic client that returns a text response."""
    with patch("sentinel.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Default: return a simple text response (no tool use)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "System is healthy. CPU: 12%, RAM: 45%, Disk: 23%."
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        yield mock_client
