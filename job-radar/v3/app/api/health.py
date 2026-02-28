"""Health check endpoints."""
from fastapi import APIRouter
from app.database import get_conn
from app.config import cfg

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    try:
        async with get_conn() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}


@router.get("/health/full")
async def health_full():
    async with get_conn() as conn:
        job_count = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status NOT IN ('expired','closed')"
        )
        last_sync = await conn.fetchval("SELECT MAX(discovered_at) FROM jobs")
        last_digest = await conn.fetchval("SELECT MAX(sent_at) FROM digest_log")

    return {
        "status": "ok",
        "version": "3.0.0",
        "active_jobs": job_count,
        "last_sync": str(last_sync) if last_sync else None,
        "last_digest": str(last_digest) if last_digest else None,
        "brave_api": "configured" if cfg.BRAVE_API_KEY else "missing",
        "telegram": "configured" if cfg.TELEGRAM_BOT_TOKEN else "missing",
        "gemini": "configured" if cfg.GEMINI_API_KEY else "missing",
    }
