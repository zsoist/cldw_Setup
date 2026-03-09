"""Sentinel main entry point — runs Telegram + Discord bots in one async event loop."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from telegram import Update

from config import SentinelConfig
from sentinel import SentinelAgent
from telegram_handler import SentinelTelegramBot

logger = logging.getLogger("sentinel")


async def _async_main():
    """Run Telegram + Discord bots concurrently in a single event loop."""
    config = SentinelConfig()
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        raise SystemExit(1)

    agent = SentinelAgent(config)
    telegram_bot = SentinelTelegramBot(config, agent)
    telegram_app = telegram_bot.build_app()

    discord_bot = None
    if config.discord_enabled and config.discord_token:
        from discord_handler import SentinelDiscordBot
        discord_bot = SentinelDiscordBot(config, agent)

    # Set up graceful shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    # Start Telegram
    async with telegram_app:
        await telegram_app.start()
        await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot started")

        if discord_bot is not None:
            # Start Discord (bot.start() connects to gateway and runs until cancelled)
            discord_task = asyncio.create_task(
                discord_bot.bot.start(config.discord_token)
            )
            logger.info("Discord bot starting...")

            # Wait for shutdown signal
            await stop_event.wait()

            # Graceful shutdown
            logger.info("Shutting down...")
            await discord_bot.bot.close()
            discord_task.cancel()
            try:
                await discord_task
            except asyncio.CancelledError:
                pass
        else:
            logger.info("Discord disabled, running Telegram-only mode")
            await stop_event.wait()

        # Stop Telegram
        await telegram_app.updater.stop()
        await telegram_app.stop()

    logger.info("Sentinel shut down cleanly")


def main():
    """Entry point."""
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
