"""Telegram bot interface for Sentinel."""
import json
import logging
from telegram import Update
from telegram.error import BadRequest
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


class SentinelTelegramBot:
    """Telegram interface for the Sentinel sysadmin bot."""

    def __init__(self, config: SentinelConfig, agent: SentinelAgent):
        self.config = config
        self.agent = agent

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is in the allowed list."""
        return user_id in self.config.allowed_user_ids

    def _build_usage_footer(self, user_id: int) -> str:
        """Build per-request usage summary for Telegram responses."""
        stats = {}
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

    async def _reply_text_safe(self, message, text: str) -> None:
        """Send markdown when possible, fallback to plain text on parse errors."""
        try:
            await message.reply_text(text, parse_mode="Markdown")
        except BadRequest as exc:
            if "can't parse entities" in str(exc).lower():
                await message.reply_text(text)
                return
            raise

    async def _reply_text_safe_chunked(self, message, text: str, chunk_size: int = 4000) -> None:
        """Send long text in Telegram-safe chunks with markdown fallback."""
        if len(text) <= chunk_size:
            await self._reply_text_safe(message, text)
            return
        for i in range(0, len(text), chunk_size):
            await self._reply_text_safe(message, text[i : i + chunk_size])

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
            "- Or just describe what you need in plain text.\n\n"
            "All requests go through the configured LLM provider with tool verification.",
            parse_mode="Markdown"
        )

    def _format_static_stats(self, user_id: int) -> str:
        """Format system status directly from tools — zero LLM cost."""
        stats = execute_system_stats()
        docker = execute_docker_status()
        lines = [
            f"*System Status*",
            f"CPU: {stats.get('cpu_percent', '?')}% | "
            f"RAM: {stats.get('memory_used_gb', '?')}/{stats.get('memory_total_gb', '?')}GB "
            f"({stats.get('memory_percent', '?')}%)",
            f"Disk: {stats.get('disk_used_gb', '?')}/{stats.get('disk_total_gb', '?')}GB "
            f"({stats.get('disk_percent', '?')}%)",
            f"Swap: {stats.get('swap_used_gb', '?')}/{stats.get('swap_total_gb', '?')}GB",
            f"Uptime: {stats.get('uptime', '?')}",
            "",
            "*Containers:*",
        ]
        for c in docker.get("containers", []):
            lines.append(f"• {c.get('name', '?')}: {c.get('status', '?')}")
        # Set zero-cost stats so footer shows 0 tokens
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(user_id, zero_stats)
        return "\n".join(lines)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Quick system status — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            response = self._format_static_stats(update.effective_user.id)
        except Exception as e:
            logger.error(f"Status command failed: {e}", exc_info=True)
            response = f"Error getting status: {str(e)[:200]}"
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def openclaw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check OpenClaw health — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            result = execute_check_openclaw_health()
            lines = [f"*OpenClaw Health*"]
            lines.append(f"Container: {result.get('container_status', '?')}")
            lines.append(f"Uptime: {result.get('uptime', '?')}")
            lines.append(f"HTTP: {result.get('http_status', '?')}")
            errors = result.get("recent_errors", [])
            if errors:
                lines.append(f"\n*Recent Errors ({len(errors)}):*")
                for e in errors[:5]:
                    lines.append(f"• {str(e)[:120]}")
            else:
                lines.append("No recent errors.")
            response = "\n".join(lines)
        except Exception as e:
            logger.error(f"OpenClaw command failed: {e}", exc_info=True)
            response = f"Error checking OpenClaw: {str(e)[:200]}"
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(update.effective_user.id, zero_stats)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run security audit — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            result = execute_check_security()
            lines = [f"*Security Audit*"]
            for section in ["ufw_status", "open_ports", "failed_ssh_attempts", "running_services"]:
                val = result.get(section, "N/A")
                label = section.replace("_", " ").title()
                if isinstance(val, list):
                    lines.append(f"\n*{label}:*")
                    for item in val[:10]:
                        lines.append(f"• {str(item)[:120]}")
                else:
                    lines.append(f"{label}: {str(val)[:200]}")
            response = "\n".join(lines)
        except Exception as e:
            logger.error(f"Security command failed: {e}", exc_info=True)
            response = f"Error running security audit: {str(e)[:200]}"
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(update.effective_user.id, zero_stats)
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
                    f"File: `{result.get('backup_file', '?')}`\n"
                    f"Size: {result.get('size_bytes', 0) / 1024 / 1024:.1f} MB"
                )
            else:
                response = f"Backup failed: {result.get('error', 'unknown')}"
        except Exception as e:
            logger.error(f"Backup command failed: {e}", exc_info=True)
            response = f"Error creating backup: {str(e)[:200]}"
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(update.effective_user.id, zero_stats)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def cost_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show API cost summary — direct tool execution, zero LLM cost."""
        if not self._is_authorized(update.effective_user.id):
            return
        try:
            args = (context.args[0] if context.args else "today")
            result = execute_cost_summary(args)
            lines = [f"*API Cost Summary ({args})*"]
            for svc_name, svc_data in result.items():
                if svc_name in ("grand_total", "daily_budget_remaining"):
                    continue
                if not isinstance(svc_data, dict):
                    continue
                in_t = svc_data.get("input_tokens", 0)
                out_t = svc_data.get("output_tokens", 0)
                usd = svc_data.get("estimated_usd", 0)
                lines.append(f"\n*{svc_name}:* {in_t}/{out_t} tokens — ${usd:.6f}")
            total = result.get("grand_total", {})
            if total:
                cop = total.get("estimated_cop", 0)
                lines.append(f"\n*Total:* ${total.get('estimated_usd', 0):.6f} USD / ${cop:,.0f} COP")
            remaining = result.get("daily_budget_remaining")
            if remaining is not None:
                lines.append(f"Daily budget remaining: ${remaining:.4f}")
            response = "\n".join(lines)
        except Exception as e:
            logger.error(f"Cost command failed: {e}", exc_info=True)
            response = f"Error getting cost summary: {str(e)[:200]}"
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(update.effective_user.id, zero_stats)
        response = self._append_usage_footer(update.effective_user.id, response)
        await self._reply_text_safe_chunked(update.message, response)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle free-text messages."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized.")
            return

        user_message = update.message.text
        logger.info(f"Message from {update.effective_user.id}: {user_message[:100]}")

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        try:
            response = self.agent.process_message(update.effective_user.id, user_message)
            response = self._append_usage_footer(update.effective_user.id, response)
            await self._reply_text_safe_chunked(update.message, response)
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            err = self._append_usage_footer(update.effective_user.id, f"Error: {str(e)[:200]}")
            await update.message.reply_text(err)

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
            logger.error(f"Config error: {e}")
        raise SystemExit(1)

    agent = SentinelAgent(config)
    bot = SentinelTelegramBot(config, agent)
    bot.run()


if __name__ == "__main__":
    main()
