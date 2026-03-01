"""Telegram command handlers."""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.database import get_conn
from app.telegram.formatters import format_job_card, format_stats, format_job_detail
from app.telegram.callbacks import build_job_buttons
from app.config import cfg
from app.telegram.conversation import process_message

logger = logging.getLogger(__name__)


def _is_authorized(update: Update) -> bool:
    """Only respond to owner or channel."""
    user_id = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else 0
    return user_id == cfg.TELEGRAM_OWNER_CHAT_ID or chat_id == cfg.TELEGRAM_CHANNEL_ID


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "🔍 Job Radar V3 — Standalone Agent\n\n"
        "Scout, don't apply. Surface the best leads.\n\n"
        "Use /help for commands."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "🔍 Job Radar Commands\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/jobs — Top 5 active jobs\n"
        "/jobs full — Top 15\n"
        "/jobs hot — Composite ≥ 70 only\n"
        "/jobs hidden — Hidden junior opportunities\n"
        "/search <query> — Free-text search\n"
        "/saved — Your saved jobs\n"
        "/applied — Application pipeline\n"
        "/stats — Pipeline health (7d)\n"
        "/health — System health\n"
        "/sync — Force discovery sync\n"
        "/help — This message"
    )


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    args = context.args or []
    mode = args[0].lower() if args else "default"

    limit = 5
    min_composite = 0
    hidden_only = False

    if mode == "full":
        limit = 15
    elif mode == "hot":
        min_composite = 70
        limit = 10
    elif mode == "hidden":
        hidden_only = True
        limit = 10

    async with get_conn() as conn:
        if hidden_only:
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status NOT IN ('dismissed', 'expired', 'closed')
                  AND j.hidden_junior = true
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $1
            """, limit)
        else:
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status NOT IN ('dismissed', 'expired', 'closed')
                  AND j.score_composite >= $1
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $2
            """, min_composite, limit)

    if not rows:
        await update.message.reply_text("No jobs found matching criteria.")
        return

    for i, row in enumerate(rows, 1):
        job = dict(row)
        text = format_job_card(job, i)
        buttons = build_job_buttons(str(job['id']))
        await update.message.reply_text(text, reply_markup=buttons, disable_web_page_preview=True)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>\nExample: /search pytorch startup")
        return

    from app.telegram.conversation import _extract_search_terms
    like_patterns, tech_terms = _extract_search_terms(query)

    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT j.*, c.name as company_name, c.ats_platform
            FROM jobs j JOIN companies c ON j.company_id = c.id
            WHERE (j.title ILIKE ANY($1::text[])
                   OR c.name ILIKE ANY($1::text[])
                   OR j.tech_stack && $2::text[]
                   OR j.description_snippet ILIKE ANY($1::text[]))
              AND j.status NOT IN ('expired', 'closed')
            ORDER BY j.score_composite DESC LIMIT 10
        """, like_patterns, tech_terms)

    if not rows:
        await update.message.reply_text(f"No jobs found for '{query}'.")
        return

    for i, row in enumerate(rows, 1):
        job = dict(row)
        text = format_job_card(job, i)
        buttons = build_job_buttons(str(job['id']))
        await update.message.reply_text(text, reply_markup=buttons, disable_web_page_preview=True)


async def cmd_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT j.*, c.name as company_name FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.status = 'saved'
            ORDER BY j.score_composite DESC LIMIT 20
        """)

    if not rows:
        await update.message.reply_text("No saved jobs. Use 💾 Save on job cards.")
        return

    text = "💾 Saved Jobs\n" + "━" * 30 + "\n"
    for i, row in enumerate(rows, 1):
        job = dict(row)
        line = f"\n{i}. {job['title']} @ {job['company_name']}\n   📊 {job['score_composite']} | 🔗 {job.get('apply_url') or job['url']}\n"
        if len(text) + len(line) > 4000:
            await update.message.reply_text(text, disable_web_page_preview=True)
            text = ""
        text += line

    if text.strip():
        await update.message.reply_text(text, disable_web_page_preview=True)


async def cmd_applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT j.*, c.name as company_name FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.status IN ('applied', 'interviewing', 'offered')
            ORDER BY j.discovered_at DESC LIMIT 20
        """)

    if not rows:
        await update.message.reply_text("No applications tracked. Use ✅ Applied on job cards.")
        return

    text = "📋 Application Pipeline\n" + "━" * 30 + "\n"
    for i, row in enumerate(rows, 1):
        job = dict(row)
        emoji = {"applied": "📤", "interviewing": "🗣", "offered": "🎉"}.get(job['status'], "📋")
        line = f"\n{emoji} {job['title']} @ {job['company_name']}\n   Status: {job['status']} | 🔗 {job.get('apply_url') or job['url']}\n"
        if len(text) + len(line) > 4000:
            await update.message.reply_text(text, disable_web_page_preview=True)
            text = ""
        text += line

    if text.strip():
        await update.message.reply_text(text, disable_web_page_preview=True)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    days = 7
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass

    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with get_conn() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at > $1", cutoff
        )
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) as count FROM jobs "
            "WHERE discovered_at > $1 GROUP BY status ORDER BY count DESC", cutoff
        )
        by_source = await conn.fetch(
            "SELECT source, COUNT(*) as count FROM jobs "
            "WHERE discovered_at > $1 GROUP BY source ORDER BY count DESC", cutoff
        )
        dismiss_reasons = await conn.fetch(
            "SELECT reason, COUNT(*) as count FROM job_feedback "
            "WHERE action = 'dismiss' AND created_at > $1 "
            "GROUP BY reason ORDER BY count DESC", cutoff
        )

    stats_data = {
        "window_days": days,
        "total_discovered": total,
        "by_status": [dict(r) for r in by_status],
        "by_source": [dict(r) for r in by_source],
        "dismiss_reasons": [dict(r) for r in dismiss_reasons],
    }

    await update.message.reply_text(format_stats(stats_data))


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    async with get_conn() as conn:
        job_count = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status NOT IN ('expired','closed')"
        )
        last_sync = await conn.fetchval("SELECT MAX(discovered_at) FROM jobs")
        last_digest = await conn.fetchval("SELECT MAX(sent_at) FROM digest_log")

    text = (
        "🏥 Job Radar V3 — Health\n"
        "━" * 30 + "\n"
        f"Status: ✅ OK\n"
        f"Active jobs: {job_count}\n"
        f"Last sync: {last_sync or 'Never'}\n"
        f"Last digest: {last_digest or 'Never'}\n"
        f"Brave API: {'✅' if cfg.BRAVE_API_KEY else '❌'}\n"
        f"Telegram: {'✅' if cfg.TELEGRAM_BOT_TOKEN else '❌'}\n"
        f"Gemini: {'✅' if cfg.GEMINI_API_KEY else '❌'}\n"
        f"Version: 3.0.0"
    )
    await update.message.reply_text(text)


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return

    await update.message.reply_text("🔄 Starting discovery sync...")
    from app.ingestion.pipeline import run_discovery_sync
    import asyncio
    stats = await run_discovery_sync()
    await update.message.reply_text(
        f"✅ Sync complete!\n"
        f"Fetched: {stats['fetched']} | New: {stats['stored']} | "
        f"Dupes: {stats['deduped']} | Errors: {stats['errors']}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages via NL conversation (Gemini-powered)."""
    if not update.message:
        return
    if not _is_authorized(update):
        return

    text = update.message.text
    if not text or not text.strip():
        return

    # Show typing indicator while Gemini processes
    await update.message.chat.send_action("typing")

    result = await process_message(text.strip(), update.effective_chat.id)

    # Send main text response
    if result.text:
        await update.message.reply_text(
            result.text, disable_web_page_preview=True
        )

    # Send job cards with inline buttons (if search/explain returned jobs)
    if result.jobs:
        for i, job in enumerate(result.jobs, 1):
            card = format_job_card(job, i)
            buttons = build_job_buttons(str(job['id']))
            await update.message.reply_text(
                card, reply_markup=buttons, disable_web_page_preview=True
            )
