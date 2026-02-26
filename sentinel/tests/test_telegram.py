"""Tests for Telegram handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
pytest.importorskip("telegram")
from telegram import Update, User, Message, Chat

from config import SentinelConfig
from sentinel import SentinelAgent
from telegram_handler import SentinelTelegramBot


@pytest.fixture
def config():
    return SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="anthropic",
        anthropic_api_key="test-key",
        model="claude-haiku-4-5",
    )


@pytest.fixture
def mock_agent():
    with patch("sentinel.Anthropic"):
        config = SentinelConfig(
            telegram_token="test-token",
            allowed_user_ids=[12345],
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        agent = SentinelAgent(config)
        agent.process_message = MagicMock(return_value="Test response")
        agent.get_last_request_stats = MagicMock(
            return_value={
                "input_tokens": 120,
                "output_tokens": 45,
                "estimated_usd": 0.00012,
                "brave_api_calls": 0,
            }
        )
        return agent


@pytest.fixture
def bot(config, mock_agent):
    return SentinelTelegramBot(config, mock_agent)


def make_update(user_id: int, text: str = "/start") -> Update:
    """Create a mock Telegram Update object."""
    user = MagicMock(spec=User)
    user.id = user_id

    chat = MagicMock(spec=Chat)
    chat.id = user_id

    message = MagicMock(spec=Message)
    message.text = text
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = message

    return update


class TestAuthorization:
    """Test user authorization checks."""

    def test_authorized_user(self, bot):
        assert bot._is_authorized(12345) is True

    def test_unauthorized_user(self, bot):
        assert bot._is_authorized(99999) is False


class TestStartCommand:
    """Test /start command handler."""

    @pytest.mark.asyncio
    async def test_authorized_start(self, bot):
        update = make_update(12345, "/start")
        context = MagicMock()
        await bot.start_command(update, context)
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Sentinel Online" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_unauthorized_start(self, bot):
        update = make_update(99999, "/start")
        context = MagicMock()
        await bot.start_command(update, context)
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Unauthorized" in call_args[0][0]


class TestMessageHandler:
    """Test free-text message handling."""

    @pytest.mark.asyncio
    async def test_authorized_message(self, bot):
        update = make_update(12345, "What is the system status?")
        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        await bot.handle_message(update, context)
        bot.agent.process_message.assert_called_once_with(12345, "What is the system status?")
        update.message.reply_text.assert_called_once()
        sent_text = update.message.reply_text.call_args[0][0]
        assert "Test response" in sent_text
        assert "Tokens used: 120/45" in sent_text
        assert "Brave api:" not in sent_text

    @pytest.mark.asyncio
    async def test_unauthorized_message(self, bot):
        update = make_update(99999, "hack the planet")
        context = MagicMock()
        await bot.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Unauthorized" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_footer_includes_brave_only_when_used(self, bot):
        update = make_update(12345, "status")
        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_chat_action = AsyncMock()

        bot.agent.get_last_request_stats.return_value = {
            "input_tokens": 200,
            "output_tokens": 100,
            "estimated_usd": 0.001,
            "brave_api_calls": 2,
        }
        await bot.handle_message(update, context)
        sent_text = update.message.reply_text.call_args[0][0]
        assert "Tokens used: 200/100" in sent_text
        assert "Brave api: 2" in sent_text


class TestConfigValidation:
    """Test configuration validation."""

    def test_valid_config(self, config):
        errors = config.validate()
        assert len(errors) == 0

    def test_missing_token(self):
        config = SentinelConfig(
            telegram_token="",
            allowed_user_ids=[12345],
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        errors = config.validate()
        assert any("SENTINEL_TELEGRAM_TOKEN" in e for e in errors)

    def test_missing_api_key(self):
        config = SentinelConfig(
            telegram_token="test-token",
            allowed_user_ids=[12345],
            provider="anthropic",
            anthropic_api_key="",
        )
        errors = config.validate()
        assert any("ANTHROPIC_API_KEY" in e for e in errors)

    def test_missing_google_api_key_for_google_provider(self):
        config = SentinelConfig(
            telegram_token="test-token",
            allowed_user_ids=[12345],
            provider="google",
            google_api_key="",
        )
        errors = config.validate()
        assert any("GEMINI_API_KEY" in e for e in errors)

    def test_google_provider_accepts_gemini_key(self):
        config = SentinelConfig(
            telegram_token="test-token",
            allowed_user_ids=[12345],
            provider="google",
            google_api_key="test-google-key",
        )
        errors = config.validate()
        assert not any("GEMINI_API_KEY" in e for e in errors)

    def test_allowed_users_parses_inline_comments(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_ALLOWED_USERS", "12345 # me, 67890 # backup")
        config = SentinelConfig(
            telegram_token="test-token",
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        assert config.allowed_user_ids == [12345, 67890]

    def test_allowed_users_ignores_non_numeric_and_empty(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_ALLOWED_USERS", "12345, abc, , 67890, -10, 9000x")
        config = SentinelConfig(
            telegram_token="test-token",
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        assert config.allowed_user_ids == [12345, 67890]

    def test_allowed_users_multi_comment_format(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_ALLOWED_USERS", "12345 # owner, 67890 # backup, # trailing")
        config = SentinelConfig(
            telegram_token="test-token",
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        assert config.allowed_user_ids == [12345, 67890]

    def test_telegram_token_parses_inline_comment(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_TELEGRAM_TOKEN", "123:abc # bot token")
        config = SentinelConfig(
            allowed_user_ids=[12345],
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        assert config.telegram_token == "123:abc"

    def test_empty_allowed_users_triggers_validation_error(self):
        config = SentinelConfig(
            telegram_token="test-token",
            allowed_user_ids=[],
            provider="anthropic",
            anthropic_api_key="test-key",
        )
        errors = config.validate()
        assert any("SENTINEL_ALLOWED_USERS" in e for e in errors)
