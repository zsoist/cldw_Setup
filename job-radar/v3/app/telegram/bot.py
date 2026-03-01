"""Telegram bot setup — long-polling, lives inside the agent container."""
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from app.config import cfg
from app.telegram.commands import (
    cmd_jobs, cmd_search, cmd_saved, cmd_applied, cmd_stats,
    cmd_health, cmd_sync, cmd_help, cmd_start, handle_message,
)
from app.telegram.callbacks import handle_callback

logger = logging.getLogger(__name__)

_application: Application | None = None


async def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    global _application
    if not cfg.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN required")

    app = Application.builder().token(cfg.TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("saved", cmd_saved))
    app.add_handler(CommandHandler("applied", cmd_applied))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("sync", cmd_sync))

    # Plain text messages (NL conversation via Gemini)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    _application = app
    logger.info("Telegram bot configured")
    return app


async def start_polling(app: Application):
    """Start long-polling. Non-blocking — runs in background."""
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True, poll_interval=2.0)
    logger.info("Telegram bot polling started")


async def stop_polling(app: Application):
    """Gracefully stop the bot."""
    if app.updater and app.updater.running:
        await app.updater.stop()
    if app.running:
        await app.stop()
    await app.shutdown()
    logger.info("Telegram bot stopped")


def get_bot() -> Application | None:
    return _application
