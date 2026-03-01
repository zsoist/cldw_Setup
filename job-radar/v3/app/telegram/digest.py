"""Digest generation and delivery to Telegram channel."""
import hashlib
import logging
from datetime import datetime, timezone
from telegram import Bot
from app.database import get_conn
from app.config import cfg, dyn
from app.telegram.formatters import format_digest
from app.telegram.callbacks import build_job_buttons

logger = logging.getLogger(__name__)


async def send_am_digest():
    """Morning digest: top jobs by composite score."""
    await _send_digest("am")


async def send_pm_digest():
    """Evening digest: new jobs discovered today + daily stats."""
    await _send_digest("pm")


async def send_weekly_report():
    """Weekly summary with pipeline stats."""
    async with get_conn() as conn:
        stats = {
            "saved": await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'saved'"),
            "applied": await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'applied'"),
            "interviewing": await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'interviewing'"),
        }
        total_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at > now() - INTERVAL '7 days'"
        )
        by_source = await conn.fetch(
            "SELECT source, COUNT(*) as count FROM jobs "
            "WHERE discovered_at > now() - INTERVAL '7 days' GROUP BY source ORDER BY count DESC"
        )

    text = (
        "📊 Job Radar — Weekly Report\n"
        "━" * 30 + "\n"
        f"New jobs this week: {total_7d}\n\n"
        "By Source:\n" +
        "\n".join(f"  {r['source']}: {r['count']}" for r in by_source) +
        f"\n\nPipeline:\n"
        f"  💾 Saved: {stats['saved']}\n"
        f"  📤 Applied: {stats['applied']}\n"
        f"  🗣 Interviewing: {stats['interviewing']}\n"
    )

    bot = Bot(token=cfg.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=cfg.TELEGRAM_CHANNEL_ID,
            text=text,
            disable_web_page_preview=True,
        )
        logger.info("Weekly report sent")
    except Exception as e:
        logger.error("Weekly report failed: %s", e)
    finally:
        await bot.shutdown()


async def _send_digest(digest_type: str):
    """Core digest logic."""
    async with get_conn() as conn:
        # Get pipeline stats for footer
        stats = {
            "saved": await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'saved'"),
            "applied": await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'applied'"),
            "interviewing": await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'interviewing'"),
        }

        # Fetch top jobs (using dynamic config for thresholds)
        rows = await conn.fetch("""
            SELECT j.*, c.name as company_name, c.ats_platform
            FROM jobs j JOIN companies c ON j.company_id = c.id
            WHERE j.status NOT IN ('dismissed', 'expired', 'closed')
              AND j.score_composite >= $1
              AND j.discovered_at > now() - INTERVAL '21 days'
              AND c.auto_suppress = false
            ORDER BY j.score_composite DESC
            LIMIT $2
        """, dyn('digest_min_composite'), dyn('digest_max_jobs'))

    if not rows:
        logger.info("No jobs above threshold for %s digest", digest_type)
        return

    jobs = [dict(r) for r in rows]

    # Idempotency: hash job IDs + date (so same jobs still get sent daily)
    job_ids = sorted(str(j['id']) for j in jobs)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest_hash = hashlib.sha256(f"{digest_type}:{date_str}:{','.join(job_ids)}".encode()).hexdigest()

    async with get_conn() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM digest_log WHERE content_hash = $1", digest_hash
        )
        if existing:
            logger.info("Digest %s already sent (hash match), skipping", digest_type)
            return

    # Format and send
    text = format_digest(jobs, digest_type, stats)

    bot = Bot(token=cfg.TELEGRAM_BOT_TOKEN)
    try:
        # Send header as one message
        # Then individual job cards with buttons
        header_end = text.find("━" * 30)
        if header_end > 0:
            header = text[:header_end + 30]
            await bot.send_message(
                chat_id=cfg.TELEGRAM_CHANNEL_ID,
                text=header,
                disable_web_page_preview=True,
            )

        # Send each job as a separate message with inline buttons
        from app.telegram.formatters import format_job_card
        for i, job in enumerate(jobs, 1):
            card_text = format_job_card(job, i)
            buttons = build_job_buttons(str(job['id']))
            await bot.send_message(
                chat_id=cfg.TELEGRAM_CHANNEL_ID,
                text=card_text,
                reply_markup=buttons,
                disable_web_page_preview=True,
            )

        # Send footer
        footer = (
            f"📊 Pipeline: {stats.get('saved', 0)} saved | "
            f"{stats.get('applied', 0)} applied | "
            f"{stats.get('interviewing', 0)} interviewing\n"
            "💡 Tip: Save or Pass jobs to improve future recommendations."
        )
        await bot.send_message(
            chat_id=cfg.TELEGRAM_CHANNEL_ID,
            text=footer,
            disable_web_page_preview=True,
        )

        # Log digest
        async with get_conn() as conn:
            saved_24h = await conn.fetchval(
                "SELECT COUNT(*) FROM job_feedback WHERE action = 'save' "
                "AND created_at > now() - INTERVAL '24 hours'"
            )
            dismissed_24h = await conn.fetchval(
                "SELECT COUNT(*) FROM job_feedback WHERE action = 'dismiss' "
                "AND created_at > now() - INTERVAL '24 hours'"
            )
            await conn.execute("""
                INSERT INTO digest_log (digest_type, jobs_shown, jobs_saved_24h, jobs_dismissed_24h, content_hash)
                VALUES ($1, $2, $3, $4, $5)
            """, digest_type, len(jobs), saved_24h, dismissed_24h, digest_hash)

        logger.info("Digest %s sent: %d jobs to channel %s", digest_type, len(jobs), cfg.TELEGRAM_CHANNEL_ID)

    except Exception as e:
        logger.error("Digest %s failed: %s", digest_type, e)
    finally:
        await bot.shutdown()
