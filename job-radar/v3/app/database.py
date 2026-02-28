import asyncpg
import logging
from contextlib import asynccontextmanager
from app.config import cfg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(cfg.DATABASE_URL, min_size=2, max_size=10)
    logger.info("Database pool initialized")


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


@asynccontextmanager
async def get_conn():
    async with _pool.acquire() as conn:
        yield conn


async def get_pool() -> asyncpg.Pool:
    return _pool
