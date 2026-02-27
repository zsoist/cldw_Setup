"""Telegram bot interface for Sentinel."""

from __future__ import annotations

import logging
import re
from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import SentinelConfig
from sentinel import SentinelAgent
from tools import (
    execute_system_stats,
    execute_docker_status,
    execute_check_openclaw_health,
    execute_check_security,
    execute_backup_openclaw,
    execute_cost_summary,
)

logger = logging.getLogger("sentinel.telegram")

# Telegram hard limit is 4096 chars. We reserve space for footer + overhead.
_MAX_CHUNK = 3800
# Characters that break Telegram Markdown v1 inside user-generated content.
_MD_ESCAPE_RE = re.compile(r"([_*\[\]`])")

# Allowed period arguments for /cost command.
_COST_PERIODS = frozenset({"today", "week", "month", "all"})


def _escape_md(text: str) -> str:
    """Escape Markdown v1 special characters in dynamic content."""
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


def _safe_str(value: object, max_len: int = 200) -> str:
    """Convert a value to an escaped, truncated string safe for Markdown."""
    raw = str(value)[:max_len]
    return _escape_md(raw)


class SentinelTelegramBot:
    """Telegram interface for the Sentinel sysadmin bot."""

    def __init__(self, config: SentinelConfig, agent: SentinelAgent):
        self.config = config
        self.agent = agent

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is in the allowed list."""
        return user_id in self.config.allowed_user_ids

    # ------------------------------------------------------------------
    # Usage footer
    # ------------------------------------------------------------------

    def _build_usage_footer(self, user_id: int) -> str:
        """Build per-request usage summary for Telegram responses.

        Footer is always sent as plain text (no Markdown) so $ and , are safe.
        """
        stats: dict = {}
        if hasattr(self.agent, "get_last_request_stats"):
            try:
                stats = self.agent.get_last_request_stats(user_id) or {}
            except Exception:
                stats = {}

        input_tokens = max(0, int(stats.get("input_tokens", 0)))
        output_tokens = max(0, int(stats.get("output_tokens", 0)))
        usd_cost = max(0.0, float(stats.get("estimated_usd", 0.0)))
        cop_cost = usd_cost * float(self.config.usd_to_cop_rate)
        brave_calls = max(0, int(stats.get("brave_api_calls", 0)))

        footer = (
            f"Tokens used: {input_tokens}/{output_tokens} - "
            f"USD ${usd_cost:.6f} / COP ${cop_cost:,.2f}"
        )
        if brave_calls > 0:
            footer += f" - Brave api: {brave_calls}"
        return footer

    def _append_usage_footer(self, user_id: int, text: str) -> str:
        base = (text or "").rstrip()
        footer = self._build_usage_footer(user_id)
        if not base:
            return footer
        return f"{base}\n\n{footer}"

    # ------------------------------------------------------------------
    # Safe message sending
    # ------------------------------------------------------------------

    async def _reply_text_safe(self, message, text: str) -> None:
        """Send text with Markdown, falling back to plain text on any parse error."""
        if not text:
            text = "(empty response)"
        try:
            await message.reply_text(text, parse_mode="Markdown")
        except BadRequest as exc:
            if "parse" in str(exc).lower() or "entity" in str(exc).lower():
                # Markdown parsing failed — retry as plain text
                try:
                    await message.reply_text(text)
                except TelegramError as inner_exc:
                    logger.error("Plain-text fallback also failed: %s", inner_exc)
                return
            raise
        except TelegramError as exc:
            # Network errors, chat not found, etc. — log and re-raise
            logger.error("Telegram send failed: %s", exc)
            raise

    async def _reply_text_safe_chunked(self, message, text: str) -> None:
        """Send long text in Telegram-safe chunks.

        Splits on newline boundaries to avoid breaking Markdown formatting.
        Chunk size accounts for Telegram's 4096 char limit with safety margin.
        """
        if not text:
            await self._reply_text_safe(message, "(empty response)")
            return

        if len(text) <= _MAX_CHUNK:
            await self._reply_text_safe(message, text)
            return

        # Split at newline boundaries to preserve Markdown structure.
        lines = text.split("\n")
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if current_len + line_len > _MAX_CHUNK and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            # If a single line exceeds chunk size, force-split it.
            if line_len > _MAX_CHUNK:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0
                for i in range(0, len(line), _MAX_CHUNK):
                    chunks.append(line[i : i + _MAX_CHUNK])
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                header = f"[{idx + 1}/{len(chunks)}]\n"
                chunk = header + chunk
            await self._reply_text_safe(message, chunk)

    # ------------------------------------------------------------------
    # Typing indicator (crash-safe)
    # ------------------------------------------------------------------

    async def _send_typing(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        """Send typing indicator. Swallows errors to avoid crashing the handler."""
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except TelegramError as exc:
            logger.debug("Typing indicator failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Zero-cost stats helper
    # ------------------------------------------------------------------

    def _set_zero_cost_stats(self, user_id: int) -> None:
        """Set zero-cost request stats for direct tool commands."""
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(user_id, zero_stats)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized. This bot is restricted.")
            return

        await update.message.reply_text(
            "*Sentinel Online*\n\n"
            "I manage your VPS infrastructure. Commands:\n"
            "- `/status` — System stats\n"
            "- `/openclaw` — OpenClaw health\n"
            "- `/security` — Security audit\n"
            "- `/backup` — Backup OpenClaw\n"
            "- `/cost` — API cost summary\n"
            "- Or just describe what you need in plain text.\n\n"
            "All requests go through the configured LLM provider with tool verification.",
            parse_mode="Markdown",
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Quick system status — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            response = self._format_static_stats(update.effective_user.id)
        except Exception as e:
            logger.error("Status command failed: %s", e, exc_info=True)
            response = f"Error getting status: {_safe_str(e)}"
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    def _format_static_stats(self, user_id: int) -> str:
        """Format system status directly from tools — zero LLM cost."""
        stats = execute_system_stats()
        docker = execute_docker_status()
        lines = [
            "*System Status*",
            (
                f"CPU: {stats.get('cpu_percent', '?')}% | "
                f"RAM: {stats.get('memory_used_gb', '?')}/{stats.get('memory_total_gb', '?')}GB "
                f"({stats.get('memory_percent', '?')}%)"
            ),
            (
                f"Disk: {stats.get('disk_used_gb', '?')}/{stats.get('disk_total_gb', '?')}GB "
                f"({stats.get('disk_percent', '?')}%)"
            ),
            f"Swap: {stats.get('swap_used_gb', '?')}/{stats.get('swap_total_gb', '?')}GB",
            f"Uptime: {stats.get('uptime', '?')}",
            "",
            "*Containers:*",
        ]
        for c in docker.get("containers", []):
            lines.append(f"• {_escape_md(str(c.get('name', '?')))}: {_escape_md(str(c.get('status', '?')))}")
        self._set_zero_cost_stats(user_id)
        return "\n".join(lines)

    async def openclaw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check OpenClaw health — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            result = execute_check_openclaw_health()
            lines = ["*OpenClaw Health*"]
            lines.append(f"Container: {_escape_md(str(result.get('status', '?')))}")
            health_badge = "✅" if result.get("gateway_ready") else "⚠️"
            lines.append(f"Health: {health_badge} {_escape_md(str(result.get('docker_health', '?')))}")
            lines.append(f"Uptime: {_escape_md(str(result.get('uptime', '?')))}")
            lines.append(f"HTTP: {_escape_md(str(result.get('http_fallback_status', '?')))}")
            errors = result.get("recent_errors", [])
            if errors:
                lines.append(f"\n*Recent Errors ({len(errors)}):*")
                for e in errors[:5]:
                    lines.append(f"• {_safe_str(e, 120)}")
            else:
                lines.append("No recent errors.")
            response = "\n".join(lines)
        except Exception as e:
            logger.error("OpenClaw command failed: %s", e, exc_info=True)
            response = f"Error checking OpenClaw: {_safe_str(e)}"
        self._set_zero_cost_stats(update.effective_user.id)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run security audit — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            result = execute_check_security()
            lines = ["*Security Audit*"]
            for section in ["ufw", "listening_ports", "failed_ssh_attempts", "running_services_count"]:
                val = result.get(section, "N/A")
                label = section.replace("_", " ").title()
                if isinstance(val, list):
                    lines.append(f"\n*{label}:*")
                    for item in val[:10]:
                        lines.append(f"• {_safe_str(item, 120)}")
                else:
                    lines.append(f"{label}: {_safe_str(val)}")
            response = "\n".join(lines)
        except Exception as e:
            logger.error("Security command failed: %s", e, exc_info=True)
            response = f"Error running security audit: {_safe_str(e)}"
        self._set_zero_cost_stats(update.effective_user.id)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger OpenClaw backup — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            result = execute_backup_openclaw()
            if result.get("status") == "success":
                response = (
                    f"*Backup Complete*\n"
                    f"File: `{_escape_md(str(result.get('path', '?')))}`\n"
                    f"Size: {result.get('size_mb', 0):.1f} MB"
                )
            else:
                response = f"Backup failed: {_safe_str(result.get('error', 'unknown'))}"
        except Exception as e:
            logger.error("Backup command failed: %s", e, exc_info=True)
            response = f"Error creating backup: {_safe_str(e)}"
        self._set_zero_cost_stats(update.effective_user.id)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def cost_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show API cost summary — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            raw_arg = context.args[0] if context.args else "today"
            period = raw_arg.lower().strip() if raw_arg.lower().strip() in _COST_PERIODS else "today"
            result = execute_cost_summary(period)
            lines = [f"*API Cost Summary ({_escape_md(period)})*"]
            for svc_name, svc_data in result.get("services", {}).items():
                if not isinstance(svc_data, dict) or "error" in svc_data:
                    if isinstance(svc_data, dict) and "error" in svc_data:
                        lines.append(f"\n*{_escape_md(str(svc_name))}:* {_safe_str(svc_data['error'])}")
                    continue
                in_t = svc_data.get("input_tokens", 0)
                out_t = svc_data.get("output_tokens", 0)
                usd = svc_data.get("usd", 0)
                lines.append(f"\n*{_escape_md(str(svc_name))}:* {in_t}/{out_t} tokens — ${usd:.6f}")
            total = result.get("total", {})
            if total:
                cop = total.get("cop", 0)
                lines.append(f"\n*Total:* ${total.get('usd', 0):.6f} USD / ${cop:,.0f} COP")
            remaining = total.get("daily_budget_remaining") if total else None
            if remaining is not None:
                lines.append(f"Daily budget remaining: ${remaining:.4f}")
            response = "\n".join(lines)
        except Exception as e:
            logger.error("Cost command failed: %s", e, exc_info=True)
            response = f"Error getting cost summary: {_safe_str(e)}"
        self._set_zero_cost_stats(update.effective_user.id)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    # ------------------------------------------------------------------
    # Free-text message handler
    # ------------------------------------------------------------------

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle free-text messages."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized.")
            return

        user_message = update.message.text
        if not user_message:
            # Non-text messages (photos, stickers, etc.) slip through despite
            # the TEXT filter in edge cases. Guard against None.
            await update.message.reply_text("I can only process text messages.")
            return

        logger.info("Message from %d: %s", update.effective_user.id, user_message[:100])

        # Show typing indicator (crash-safe)
        await self._send_typing(context, update.effective_chat.id)

        try:
            response = self.agent.process_message(update.effective_user.id, user_message)
            response = self._append_usage_footer(update.effective_user.id, response)
            await self._reply_text_safe_chunked(update.message, response)
        except TelegramError as e:
            # Telegram delivery failure (network, chat deleted, etc.)
            logger.error("Telegram delivery error: %s", e, exc_info=True)
        except Exception as e:
            logger.error("Error processing message: %s", e, exc_info=True)
            try:
                err_text = f"Error: {_safe_str(e)}"
                err = self._append_usage_footer(update.effective_user.id, err_text)
                await update.message.reply_text(err)
            except TelegramError as send_exc:
                logger.error("Failed to send error message: %s", send_exc)

    # ------------------------------------------------------------------
    # Bot runner
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the Telegram bot."""
        app = Application.builder().token(self.config.telegram_token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("openclaw", self.openclaw_command))
        app.add_handler(CommandHandler("security", self.security_command))
        app.add_handler(CommandHandler("backup", self.backup_command))
        app.add_handler(CommandHandler("cost", self.cost_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Sentinel Telegram bot starting...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Entry point."""
    config = SentinelConfig()
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        raise SystemExit(1)

    agent = SentinelAgent(config)
    bot = SentinelTelegramBot(config, agent)
    bot.run()


if __name__ == "__main__":
    main()
