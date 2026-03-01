"""Job Radar V3 — Standalone Agent. FastAPI + Telegram Bot + APScheduler."""
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import cfg, load_dynamic_config
from app.database import init_pool, close_pool
from app.api.health import router as health_router
from app.api.routes import router as api_router
from app.scheduler import setup_scheduler
from app.telegram.bot import create_bot, start_polling, stop_polling

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("job-radar")

_bot_app = None
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_app, _scheduler

    # Startup
    logger.info("Job Radar V3 starting...")

    # 1. Database
    await init_pool()
    logger.info("Database pool ready")

    # 1b. Dynamic config (user-tweakable settings from DB)
    await load_dynamic_config()

    # 2. Scheduler
    _scheduler = setup_scheduler()
    _scheduler.start()
    logger.info("Scheduler started")

    # 3. Telegram bot
    if cfg.TELEGRAM_BOT_TOKEN:
        try:
            _bot_app = await create_bot()
            await start_polling(_bot_app)
            logger.info("Telegram bot started")
        except Exception as e:
            logger.error("Telegram bot failed to start: %s", e)
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set, bot disabled")

    logger.info("Job Radar V3 ready — API on :8080, Telegram polling active")

    yield

    # Shutdown
    logger.info("Job Radar V3 shutting down...")

    if _scheduler:
        _scheduler.shutdown(wait=False)
    if _bot_app:
        await stop_polling(_bot_app)
    await close_pool()

    logger.info("Job Radar V3 stopped")


app = FastAPI(title="Job Radar V3", version="3.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(api_router)
