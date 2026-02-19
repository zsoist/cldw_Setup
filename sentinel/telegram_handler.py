"""Telegram bot interface for Sentinel."""
import logging
from telegram import Update
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
            "All requests go through Claude with tool verification.",
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
        await update.message.reply_text(response, parse_mode="Markdown")

    async def openclaw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check OpenClaw health."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Check OpenClaw gateway health: is it running, any recent errors, HTTP status."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run security audit."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Run a security audit: UFW status, failed SSH attempts, open ports, running services."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger OpenClaw backup."""
        if not self._is_authorized(update.effective_user.id):
            return
        response = self.agent.process_message(
            update.effective_user.id,
            "Create a backup of OpenClaw's config and workspace. Report the file path and size."
        )
        await update.message.reply_text(response, parse_mode="Markdown")

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
            # Telegram has a 4096 char limit per message
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i + 4000], parse_mode="Markdown")
            else:
                await update.message.reply_text(response, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await update.message.reply_text(f"Error: {str(e)[:200]}")

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
