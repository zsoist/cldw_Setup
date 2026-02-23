"""Tests for Sentinel configuration parsing and validation."""

from config import SentinelConfig


def test_valid_anthropic_config():
    config = SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="anthropic",
        anthropic_api_key="test-key",
    )
    assert config.validate() == []


def test_missing_anthropic_api_key():
    config = SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="anthropic",
        anthropic_api_key="",
    )
    errors = config.validate()
    assert any("ANTHROPIC_API_KEY" in error for error in errors)


def test_missing_google_api_key():
    config = SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="google",
        google_api_key="",
    )
    errors = config.validate()
    assert any("GEMINI_API_KEY" in error for error in errors)


def test_allowed_users_parses_inline_comments(monkeypatch):
    monkeypatch.setenv("SENTINEL_ALLOWED_USERS", "12345 # owner, 67890 # backup")
    config = SentinelConfig(
        telegram_token="test-token",
        provider="anthropic",
        anthropic_api_key="test-key",
    )
    assert config.allowed_user_ids == [12345, 67890]
