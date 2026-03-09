"""Job Radar V3 — Data Engine. FastAPI + APScheduler (no Telegram, delivery via OpenClaw)."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import cfg, load_dynamic_config
from app.database import init_pool, close_pool
from app.api.health import router as health_router
from app.api.routes import router as api_router
from app.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("job-radar")

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    # Startup
    logger.info("Job Radar V3 starting...")

    # 1. Database
    await init_pool()
    logger.info("Database pool ready")

    # 1b. Dynamic config (user-tweakable settings from DB)
    await load_dynamic_config()

    # 2. Scheduler (data ops only: discovery, watchlist, cleanup)
    _scheduler = setup_scheduler()
    _scheduler.start()
    logger.info("Scheduler started")

    logger.info("Job Radar V3 ready — API on :8080, data engine mode")

    yield

    # Shutdown
    logger.info("Job Radar V3 shutting down...")

    if _scheduler:
        _scheduler.shutdown(wait=False)
    await close_pool()

    logger.info("Job Radar V3 stopped")


app = FastAPI(title="Job Radar V3", version="3.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(api_router)
