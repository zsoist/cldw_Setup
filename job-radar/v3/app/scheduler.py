"""APScheduler setup — no OpenClaw cron dependency."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.ingestion.pipeline import run_discovery_sync, run_watchlist_sync, cleanup_expired
from app.telegram.digest import send_am_digest, send_pm_digest, send_weekly_report

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def setup_scheduler() -> AsyncIOScheduler:
    global _scheduler
    scheduler = AsyncIOScheduler()

    # Discovery sync — 2x daily (was 4x; job boards refresh 1-2x/day max)
    scheduler.add_job(
        run_discovery_sync,
        CronTrigger(hour='5,17', timezone='UTC'),
        id='discovery_sync',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # AM Digest — 08:00 COT = 13:00 UTC
    scheduler.add_job(
        send_am_digest,
        CronTrigger(hour=13, minute=0, timezone='UTC'),
        id='digest_am',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # PM Digest — 18:00 COT = 23:00 UTC
    scheduler.add_job(
        send_pm_digest,
        CronTrigger(hour=23, minute=0, timezone='UTC'),
        id='digest_pm',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # Watchlist sync — 1x daily (was 2x; companies don't post every 12h)
    scheduler.add_job(
        run_watchlist_sync,
        CronTrigger(hour='7', timezone='UTC'),
        id='watchlist_sync',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # Cleanup expired jobs + dedup index — daily
    scheduler.add_job(
        cleanup_expired,
        CronTrigger(hour=4, timezone='UTC'),
        id='cleanup',
        max_instances=1,
    )

    # Weekly report — Saturday 18:00 COT = Saturday 23:00 UTC
    scheduler.add_job(
        send_weekly_report,
        CronTrigger(day_of_week='sat', hour=23, timezone='UTC'),
        id='weekly_report',
        max_instances=1,
    )

    _scheduler = scheduler
    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
    return scheduler


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def pause_scheduler() -> str:
    """Pause all scheduled jobs. Returns status message."""
    if not _scheduler:
        return "Scheduler not initialized."
    for job in _scheduler.get_jobs():
        job.pause()
    logger.info("All scheduler jobs paused")
    return f"⏸ Paused {len(_scheduler.get_jobs())} scheduled jobs."


def resume_scheduler() -> str:
    """Resume all scheduled jobs. Returns status message."""
    if not _scheduler:
        return "Scheduler not initialized."
    for job in _scheduler.get_jobs():
        job.resume()
    logger.info("All scheduler jobs resumed")
    return f"▶️ Resumed {len(_scheduler.get_jobs())} scheduled jobs."


def get_scheduler_status() -> str:
    """Get human-readable scheduler status."""
    if not _scheduler:
        return "Scheduler not initialized."
    lines = ["📋 Scheduled Jobs", "━" * 30]
    for job in _scheduler.get_jobs():
        state = "⏸ paused" if job.next_run_time is None else f"▶️ next: {job.next_run_time.strftime('%H:%M UTC')}"
        lines.append(f"  {job.id}: {state}")
    return "\n".join(lines)
