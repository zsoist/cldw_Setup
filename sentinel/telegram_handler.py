"""Telegram bot interface for Sentinel."""
import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import SentinelConfig
from sentinel import SentinelAgent

logger = logging.getLogger("sentinel.telegram")


class SentinelTelegramBot:
    """Telegram interface for the Sentinel sysadmin bot."""

    def __init__(self, config: SentinelConfig, agent: SentinelAgent):
        self.config = config
        self.agent = agent

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is in the allowed list."""
        return user_id in self.config.allowed_user_ids

    def _build_usage_footer(self, user_id: int) -> str:
        """Build per-request usage summary for Telegram responses."""
        stats = {}
        if hasattr(self.agent, "get_last_request_stats"):
            try:
                stats = self.agent.get_last_request_stats(user_id) or {}
            except Exception:
                stats = {}

        input_tokens = max(0, int(stats.get("input_tokens", 0)))
        output_tokens = max(0, int(stats.get("output_tokens", 0)))
        usd_cost = max(0.0, float(stats.get("estimated_usd", 0.0)))
        cop_cost = usd_cost * float(self.config.usd_to_cop_rate)
        brave_calls = max(0, int(stats.get("brave_api_calls", 0)))

        footer = (
            f"Tokens used: {input_tokens}/{output_tokens} - "
            f"USD ${usd_cost:.6f} / COP ${cop_cost:,.2f}"
        )
        if brave_calls > 0:
            footer += f" - Brave api: {brave_calls}"
        return footer

    def _append_usage_footer(self, user_id: int, text: str) -> str:
        base = (text or "").rstrip()
        footer = self._build_usage_footer(user_id)
        if not base:
            return footer
        return f"{base}\n\n{footer}"

    async def _reply_text_safe(self, message, text: str) -> None:
        """Send markdown when possible, fallback to plain text on parse errors."""
        try:
            await message.reply_text(text, parse_mode="Markdown")
        except BadRequest as exc:
            if "can't parse entities" in str(exc).lower():
                await message.reply_text(text)
                return
            raise

    async def _reply_text_safe_chunked(self, message, text: str, chunk_size: int = 4000) -> None:
        """Send long text in Telegram-safe chunks with markdown fallback."""
        if len(text) <= chunk_size:
            await self._reply_text_safe(message, text)
            return
        for i in range(0, len(text), chunk_size):
            await self._reply_text_safe(message, text[i : i + chunk_size])

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized. This bot is restricted.")
            return

        await update.message.reply_text(
            "*Sentinel Online*\n\n"
            "I manage your VPS infrastructure. Commands:\n"
            "- `/status` — System stats\n"
            "- `/openclaw` — OpenClaw health\n"
            "- `/security` — Security audit\n"
            "- `/backup` — Backup OpenClaw\n"
            "- Or just describe what you need in plain text.\n\n"
            "All requests go through the configured LLM provider with tool verification.",
            parse_mode="Markdown"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Quick system status."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Give me a quick system status: CPU, RAM, disk, and Docker containers. Be concise."
        )
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def openclaw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check OpenClaw health."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Check OpenClaw gateway health: is it running, any recent errors, HTTP status."
        )
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run security audit."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Run a security audit: UFW status, failed SSH attempts, open ports, running services."
        )
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger OpenClaw backup."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Create a backup of OpenClaw's config and workspace. Report the file path and size."
        )
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle free-text messages."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized.")
            return

        user_message = update.message.text
        logger.info(f"Message from {update.effective_user.id}: {user_message[:100]}")

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        try:
            response = self.agent.process_message(update.effective_user.id, user_message)
            response = self._append_usage_footer(update.effective_user.id, response)
            await self._reply_text_safe_chunked(update.message, response)
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            err = self._append_usage_footer(update.effective_user.id, f"Error: {str(e)[:200]}")
            await update.message.reply_text(err)

    def run(self) -> None:
        """Start the Telegram bot."""
        app = Application.builder().token(self.config.telegram_token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("openclaw", self.openclaw_command))
        app.add_handler(CommandHandler("security", self.security_command))
        app.add_handler(CommandHandler("backup", self.backup_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Sentinel Telegram bot starting...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Entry point."""
    config = SentinelConfig()
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error(f"Config error: {e}")
        raise SystemExit(1)

    agent = SentinelAgent(config)
    bot = SentinelTelegramBot(config, agent)
    bot.run()


if __name__ == "__main__":
    main()
