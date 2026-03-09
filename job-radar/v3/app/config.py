import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Config:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://jobradar:jobradar@job-radar-db:5432/jobradar")
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    BRAVE_RESULTS_PER_QUERY: int = int(os.getenv("BRAVE_RESULTS_PER_QUERY", "10"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ENRICHMENT_MODEL: str = os.getenv("ENRICHMENT_MODEL", "gemini-2.5-flash")
    JOB_MAX_AGE_DAYS: int = int(os.getenv("JOB_MAX_AGE_DAYS", "21"))
    JOB_STALE_WARNING_DAYS: int = int(os.getenv("JOB_STALE_WARNING_DAYS", "14"))
    DIGEST_MIN_COMPOSITE: int = int(os.getenv("DIGEST_MIN_COMPOSITE", "38"))
    DIGEST_MAX_JOBS: int = int(os.getenv("DIGEST_MAX_JOBS", "12"))
    DEDUP_FUZZY_THRESHOLD: float = float(os.getenv("DEDUP_FUZZY_THRESHOLD", "0.75"))
    DEDUP_WINDOW_DAYS: int = int(os.getenv("DEDUP_WINDOW_DAYS", "60"))


cfg = Config()


# ── Dynamic Config (DB-backed, user-tweakable via NL) ────────────

DYNAMIC_DEFAULTS: dict[str, int] = {
    'weight_opportunity': 30,
    'weight_junior': 30,
    'weight_colombia': 40,
    'digest_min_composite': cfg.DIGEST_MIN_COMPOSITE,
    'digest_max_jobs': cfg.DIGEST_MAX_JOBS,
    'job_max_age_days': cfg.JOB_MAX_AGE_DAYS,
}

_dynamic_cache: dict[str, int] = {}


async def load_dynamic_config():
    """Load user_config from DB into cache. Call at startup after DB pool is ready."""
    from app.database import get_conn
    try:
        async with get_conn() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
            """)
            rows = await conn.fetch("SELECT key, value FROM user_config")

        for row in rows:
            key = row['key']
            if key in DYNAMIC_DEFAULTS:
                try:
                    _dynamic_cache[key] = int(row['value'])
                except ValueError:
                    _dynamic_cache[key] = int(float(row['value']))
        if _dynamic_cache:
            logger.info("Dynamic config loaded: %s", _dynamic_cache)
    except Exception as e:
        logger.warning("Failed to load dynamic config: %s", e)


def dyn(key: str) -> int:
    """Get a dynamic config value (from cache, falling back to default)."""
    return _dynamic_cache.get(key, DYNAMIC_DEFAULTS.get(key, 0))


async def set_dynamic(key: str, value: int):
    """Set a dynamic config value (persists to DB + updates cache)."""
    if key not in DYNAMIC_DEFAULTS:
        raise ValueError(f"Unknown config key: {key}")
    value = int(value)
    _dynamic_cache[key] = value

    from app.database import get_conn
    async with get_conn() as conn:
        await conn.execute("""
            INSERT INTO user_config (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = now()
        """, key, str(value))
    logger.info("Dynamic config set: %s = %s", key, value)
