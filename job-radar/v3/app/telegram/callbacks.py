"""Telegram inline button callback handlers."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.database import get_conn
from app.telegram.formatters import format_job_detail

logger = logging.getLogger(__name__)


def build_job_buttons(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💾 Save", callback_data=f"save:{job_id}"),
        InlineKeyboardButton("❌ Pass", callback_data=f"pass:{job_id}"),
        InlineKeyboardButton("📋 Detail", callback_data=f"detail:{job_id}"),
        InlineKeyboardButton("✅ Applied", callback_data=f"applied:{job_id}"),
    ]])


def build_dismiss_buttons(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👴 Senior", callback_data=f"dismiss:{job_id}:senior"),
            InlineKeyboardButton("🌍 Not COL", callback_data=f"dismiss:{job_id}:geo"),
            InlineKeyboardButton("🔧 Stack", callback_data=f"dismiss:{job_id}:stack"),
        ],
        [
            InlineKeyboardButton("🏢 Company", callback_data=f"dismiss:{job_id}:company"),
            InlineKeyboardButton("💰 Pay", callback_data=f"dismiss:{job_id}:comp"),
            InlineKeyboardButton("🔄 Dupe", callback_data=f"dismiss:{job_id}:dupe"),
        ],
        [
            InlineKeyboardButton("⏳ Old", callback_data=f"dismiss:{job_id}:stale"),
            InlineKeyboardButton("❓ Other", callback_data=f"dismiss:{job_id}:other"),
        ],
    ])


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all inline button callbacks."""
    query = update.callback_query
    data = query.data
    parts = data.split(":")
    action = parts[0]
    job_id = parts[1] if len(parts) > 1 else ""

    try:
        if action == "save":
            async with get_conn() as conn:
                await conn.execute("UPDATE jobs SET status = 'saved' WHERE id = $1::uuid", job_id)
                await conn.execute(
                    "INSERT INTO job_feedback (job_id, action) VALUES ($1::uuid, 'save')", job_id
                )
            await query.answer("💾 Saved!")

        elif action == "pass":
            await query.edit_message_reply_markup(build_dismiss_buttons(job_id))
            await query.answer("Select reason:")

        elif action == "dismiss":
            reason = parts[2] if len(parts) > 2 else "other"
            async with get_conn() as conn:
                await conn.execute("UPDATE jobs SET status = 'dismissed' WHERE id = $1::uuid", job_id)
                await conn.execute(
                    "INSERT INTO job_feedback (job_id, action, reason) VALUES ($1::uuid, 'dismiss', $2)",
                    job_id, reason
                )
                # Check company auto-suppress
                company_dismissals = await conn.fetchval("""
                    SELECT COUNT(*) FROM job_feedback f
                    JOIN jobs j ON f.job_id = j.id
                    WHERE j.company_id = (SELECT company_id FROM jobs WHERE id = $1::uuid)
                      AND f.reason = 'company'
                      AND f.created_at > now() - INTERVAL '90 days'
                """, job_id)
                if company_dismissals >= 3:
                    await conn.execute("""
                        UPDATE companies SET auto_suppress = true,
                            suppress_reason = 'Auto: 3+ company dismissals'
                        WHERE id = (SELECT company_id FROM jobs WHERE id = $1::uuid)
                    """, job_id)

            await query.edit_message_reply_markup(
                InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"❌ Passed ({reason})", callback_data="noop"),
                    InlineKeyboardButton("↩️ Undo", callback_data=f"undo:{job_id}"),
                ]])
            )
            await query.answer(f"❌ Passed ({reason})")

        elif action == "detail":
            async with get_conn() as conn:
                row = await conn.fetchrow("""
                    SELECT j.*, c.name as company_name, c.ats_platform, c.careers_url
                    FROM jobs j JOIN companies c ON j.company_id = c.id
                    WHERE j.id = $1::uuid
                """, job_id)

            if row:
                text = format_job_detail(dict(row))
                await query.message.reply_text(
                    text, disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("💾 Save", callback_data=f"save:{job_id}"),
                        InlineKeyboardButton("✅ Applied", callback_data=f"applied:{job_id}"),
                        InlineKeyboardButton("🔙 Back", callback_data="noop"),
                    ]])
                )
            await query.answer("Details ↓")

        elif action == "applied":
            async with get_conn() as conn:
                await conn.execute("UPDATE jobs SET status = 'applied' WHERE id = $1::uuid", job_id)
                await conn.execute(
                    "INSERT INTO job_feedback (job_id, action) VALUES ($1::uuid, 'applied')", job_id
                )
            await query.edit_message_reply_markup(
                InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Applied!", callback_data="noop"),
                ]])
            )
            await query.answer("✅ Marked as applied!")

        elif action == "undo":
            async with get_conn() as conn:
                await conn.execute("UPDATE jobs SET status = 'new' WHERE id = $1::uuid", job_id)
                await conn.execute(
                    "DELETE FROM job_feedback WHERE job_id = $1::uuid AND action = 'dismiss' "
                    "AND created_at = (SELECT MAX(created_at) FROM job_feedback WHERE job_id = $1::uuid AND action = 'dismiss')",
                    job_id
                )
            await query.edit_message_reply_markup(build_job_buttons(job_id))
            await query.answer("↩️ Undone")

        elif action == "noop":
            await query.answer()

    except Exception as e:
        logger.error("Callback error (%s): %s", data, e)
        await query.answer(f"Error: {str(e)[:100]}")
