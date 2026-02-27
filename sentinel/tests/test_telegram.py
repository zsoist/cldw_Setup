"""Tests for Telegram handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
pytest.importorskip("telegram")
from telegram import Update, User, Message, Chat
from telegram.error import BadRequest, TelegramError

from config import SentinelConfig
from sentinel import SentinelAgent
from telegram_handler import SentinelTelegramBot, _escape_md, _safe_str, _MAX_CHUNK


@pytest.fixture
def config():
    return SentinelConfig(
        telegram_token="test-token",
        allowed_user_ids=[12345],
        provider="anthropic",
        anthropic_api_key="test-key",
        model="claude-sonnet-4-6",
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


class TestEscapeMd:
    """Test Markdown v1 special character escaping."""

    def test_escapes_underscores(self):
        assert _escape_md("hello_world") == r"hello\_world"

    def test_escapes_asterisks(self):
        assert _escape_md("*bold*") == r"\*bold\*"

    def test_escapes_backticks(self):
        assert _escape_md("`code`") == r"\`code\`"

    def test_escapes_brackets(self):
        assert _escape_md("[link](url)") == r"\[link\](url)"

    def test_escapes_multiple_chars(self):
        assert _escape_md("a_b*c[d]e`f") == r"a\_b\*c\[d\]e\`f"

    def test_plain_text_unchanged(self):
        assert _escape_md("hello world 123") == "hello world 123"

    def test_empty_string(self):
        assert _escape_md("") == ""

    def test_dollar_signs_not_escaped(self):
        # Dollar signs are safe in Markdown v1 (unlike MarkdownV2)
        assert _escape_md("$100.00") == "$100.00"


class TestSafeStr:
    """Test safe string conversion with escaping and truncation."""

    def test_truncates_long_strings(self):
        result = _safe_str("a" * 500, max_len=10)
        assert len(result) <= 15  # 10 chars + potential escapes

    def test_escapes_special_chars(self):
        result = _safe_str("error_in_module")
        assert r"\_" in result

    def test_handles_non_string_input(self):
        result = _safe_str(42)
        assert result == "42"

    def test_handles_exception_object(self):
        result = _safe_str(ValueError("test_error"))
        assert "test" in result
        assert r"\_" in result  # underscore escaped


class TestChunking:
    """Test message chunking for Telegram's 4096-char limit."""

    @pytest.mark.asyncio
    async def test_short_message_no_chunking(self, bot):
        update = make_update(12345)
        await bot._reply_text_safe_chunked(update.message, "short message")
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_message_chunked(self, bot):
        # Create a message that exceeds _MAX_CHUNK
        lines = ["Line " + str(i) for i in range(_MAX_CHUNK // 6)]
        long_text = "\n".join(lines)
        assert len(long_text) > _MAX_CHUNK

        update = make_update(12345)
        await bot._reply_text_safe_chunked(update.message, long_text)
        assert update.message.reply_text.call_count >= 2

        # Each chunk should have a [N/M] header
        first_call = update.message.reply_text.call_args_list[0]
        assert "[1/" in first_call[0][0]

    @pytest.mark.asyncio
    async def test_empty_message_handled(self, bot):
        update = make_update(12345)
        await bot._reply_text_safe_chunked(update.message, "")
        update.message.reply_text.assert_called_once()
        assert "(empty response)" in update.message.reply_text.call_args[0][0]


class TestSendTyping:
    """Test crash-safe typing indicator."""

    @pytest.mark.asyncio
    async def test_typing_success(self, bot):
        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        await bot._send_typing(context, 12345)
        context.bot.send_chat_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_typing_error_swallowed(self, bot):
        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_chat_action = AsyncMock(side_effect=TelegramError("forbidden"))
        # Should NOT raise
        await bot._send_typing(context, 12345)


class TestNoneMessageGuard:
    """Test that non-text messages are handled gracefully."""

    @pytest.mark.asyncio
    async def test_none_text_returns_error(self, bot):
        update = make_update(12345)
        update.message.text = None  # Simulate a photo/sticker message
        context = MagicMock()
        await bot.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        assert "text messages" in update.message.reply_text.call_args[0][0]


class TestMarkdownFallback:
    """Test Markdown parse error fallback to plain text."""

    @pytest.mark.asyncio
    async def test_markdown_parse_error_falls_back(self, bot):
        update = make_update(12345)
        # First call raises parse error, second (plain text) succeeds
        update.message.reply_text = AsyncMock(
            side_effect=[BadRequest("Can't parse entities"), None]
        )
        await bot._reply_text_safe(update.message, "test *broken markdown")
        assert update.message.reply_text.call_count == 2
        # Second call should NOT have parse_mode
        second_call = update.message.reply_text.call_args_list[1]
        assert "parse_mode" not in (second_call[1] if second_call[1] else {})
