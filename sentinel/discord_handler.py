"""Discord bot interface for Sentinel."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands

from config import SentinelConfig
from sentinel import SentinelAgent
from tools import (
    execute_system_stats,
    execute_docker_status,
    execute_check_openclaw_health,
    execute_check_security,
    execute_backup_openclaw,
    execute_cost_summary,
    execute_list_scheduled_tasks,
)

logger = logging.getLogger("sentinel.discord")

# Discord hard limit is 2000 chars. Reserve space for footer + overhead.
_MAX_CHUNK = 1900

# Allowed period arguments for /cost command.
_COST_PERIODS = frozenset({"today", "week", "month", "all"})


class SentinelDiscordBot:
    """Discord interface for the Sentinel sysadmin bot."""

    def __init__(self, config: SentinelConfig, agent: SentinelAgent):
        self.config = config
        self.agent = agent

        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.bot)

        self._register_events()
        self._register_commands()

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is in the allowed Discord user list."""
        return user_id in self.config.allowed_discord_user_ids

    def _is_sentinel_channel(self, channel_id: int) -> bool:
        """Check if the message/interaction is in the designated Sentinel channel.

        Returns True if:
          - No channel restriction is configured (discord_channel_id == 0)
          - The channel matches the configured sentinel channel
        """
        if not self.config.discord_channel_id:
            return True
        return channel_id == self.config.discord_channel_id

    # ------------------------------------------------------------------
    # Usage footer
    # ------------------------------------------------------------------

    def _build_usage_footer(self, user_id: int) -> str:
        """Build per-request usage summary for Discord responses."""
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
    # Zero-cost stats helper
    # ------------------------------------------------------------------

    def _set_zero_cost_stats(self, user_id: int) -> None:
        """Set zero-cost request stats for direct tool commands."""
        zero_stats = self.agent._new_request_stats()
        zero_stats["status"] = "cached"
        self.agent._store_last_request_stats(user_id, zero_stats)

    def _runtime_provider_model(self) -> tuple[str, str]:
        """Return the configured runtime provider/model in user-facing form."""
        provider = str(getattr(self.config, "provider", "openai") or "openai").strip().lower()
        if provider in {"codex", "openai-codex"}:
            provider = "openai"
        model = str(getattr(self.config, "model", "gpt-5-codex") or "gpt-5-codex").strip()
        if provider == "openai" and ("codex" in model.lower() or model.startswith("openai-codex/")):
            model = "gpt-5-codex"
        if provider == "google" and model in {"flash", "gemini-flash"}:
            model = "gemini-2.5-flash"
        return provider, model

    # ------------------------------------------------------------------
    # Safe chunked reply
    # ------------------------------------------------------------------

    async def _reply_chunked(self, target: Any, text: str) -> None:
        """Send text in Discord-safe chunks (max 1900 chars).

        target can be an Interaction or a Message.
        """
        if not text:
            text = "(empty response)"

        # Split at newline boundaries to preserve formatting.
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

        if not chunks:
            chunks = ["(empty response)"]

        # Send first chunk — handle Interaction vs Message differently
        is_interaction = isinstance(target, discord.Interaction)

        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                header = f"[{idx + 1}/{len(chunks)}]\n"
                chunk = header + chunk

            if is_interaction and idx == 0:
                if target.response.is_done():
                    await target.followup.send(chunk)
                else:
                    await target.response.send_message(chunk)
            elif is_interaction:
                await target.followup.send(chunk)
            else:
                await target.channel.send(chunk)

    # ------------------------------------------------------------------
    # Formatting helpers (reuse telegram_handler patterns, no MD escaping)
    # ------------------------------------------------------------------

    def _format_static_stats(self, user_id: int) -> str:
        """Format system status directly from tools — zero LLM cost."""
        stats = execute_system_stats()
        docker = execute_docker_status()
        lines = [
            "**System Status**",
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
            "**Containers:**",
        ]
        for c in docker.get("containers", []):
            name = str(c.get("name", "?"))
            status = str(c.get("status", "?"))
            cpu = c.get("cpu_percent")
            mem = c.get("memory_mb")
            mem_limit = c.get("memory_limit_mb")
            if cpu is not None and mem is not None:
                lines.append(
                    f"\u2022 {name}: {status} "
                    f"\u2014 CPU {cpu}% "
                    f"\u2014 RAM {mem}/{int(mem_limit)}MB"
                )
            else:
                lines.append(f"\u2022 {name}: {status}")
        self._set_zero_cost_stats(user_id)
        return "\n".join(lines)

    @staticmethod
    def _format_cost_dashboard(result: dict) -> str:
        """Build a rich cost dashboard for Discord."""
        period = result.get("period", "today")
        period_labels = {"today": "Today", "week": "This Week", "month": "This Month", "all": "All Time"}
        period_label = period_labels.get(period, period.title())

        lines = [f"VPS Cost Dashboard \u2014 {period_label}"]
        lines.append("=" * 32)

        services = result.get("services", {})
        svc_configs = [
            ("sentinel", "Sentinel", False),
            ("openclaw", "OpenClaw Gateway", True),
            ("job_radar", "Job Radar", True),
        ]

        for svc_key, svc_label, is_estimated in svc_configs:
            svc = services.get(svc_key, {})
            if not isinstance(svc, dict):
                continue

            if "error" in svc:
                lines.append(f"\n{svc_label}: {svc['error']}")
                continue

            est_tag = " (est)" if svc.get("is_estimate") else ""
            cost_key = "est_usd" if svc.get("is_estimate") else "usd"
            in_key = "est_input_tokens" if svc.get("is_estimate") else "input_tokens"
            out_key = "est_output_tokens" if svc.get("is_estimate") else "output_tokens"

            cost = float(svc.get(cost_key, 0))
            in_tokens = int(svc.get(in_key, 0))
            out_tokens = int(svc.get(out_key, 0))
            calls = int(svc.get("runs", svc.get("calls", 0)))
            errors = int(svc.get("errors", 0))
            brave = int(svc.get("brave_calls", 0))

            status = svc.get("status", "")
            if status == "running":
                status_icon = "[OK]"
            elif status == "not_found":
                status_icon = "[DOWN]"
            elif not svc.get("is_estimate"):
                status_icon = "[OK]"
            else:
                status_icon = ""

            lines.append(f"\n{svc_label} {status_icon}")

            by_model = svc.get("by_model", {})
            if by_model:
                model_parts = []
                for m, md in by_model.items():
                    m_runs = md.get("runs", md.get("calls", 0))
                    m_cost = md.get("est_usd", md.get("usd", 0))
                    model_parts.append(f"  {m}: {m_runs} calls ${m_cost:.4f}")
                lines.extend(model_parts)
            elif calls > 0:
                lines.append(f"  Calls: {calls}")

            if in_tokens > 0 or out_tokens > 0:
                in_k = f"{in_tokens/1000:.1f}K" if in_tokens >= 1000 else str(in_tokens)
                out_k = f"{out_tokens/1000:.1f}K" if out_tokens >= 1000 else str(out_tokens)
                lines.append(f"  Tokens: {in_k} in / {out_k} out")

            lines.append(f"  Cost{est_tag}: ${cost:.4f}")

            extras = []
            if errors > 0:
                extras.append(f"Errors: {errors}")
            if brave > 0:
                extras.append(f"Brave: {brave}")
            if extras:
                lines.append(f"  {' | '.join(extras)}")

        total = result.get("total", {})
        if total:
            lines.append("")
            lines.append("-" * 32)
            t_usd = float(total.get("usd", 0))
            t_cop = float(total.get("cop", 0))
            t_runs = int(total.get("total_runs", 0))
            has_est = total.get("has_estimates", False)

            est_note = " ~" if has_est else " "
            lines.append(f"TOTAL:{est_note}${t_usd:.4f} USD / ${t_cop:,.0f} COP")
            lines.append(f"API calls: {t_runs}")

            remaining = total.get("daily_budget_remaining")
            pct = total.get("budget_pct_used")
            if remaining is not None and pct is not None:
                filled = max(0, min(20, int(pct / 5)))
                bar = "#" * filled + "-" * (20 - filled)
                lines.append(f"Budget: [{bar}] {pct:.1f}%")
                lines.append(f"Remaining: ${remaining:.4f} of $5.00")

            if has_est:
                lines.append("\n(~) = estimated from Docker log API call counts")

        return "\n".join(lines)

    @staticmethod
    def _cron_to_human(expr: str, tz: str = "UTC") -> str:
        """Convert cron expression to human-readable schedule."""
        parts = expr.split()
        if len(parts) < 5:
            return expr

        minute, hour, dom, month, dow = parts[:5]

        def _fmt_time(h: str, m: str, src_tz: str) -> str:
            if h == "*" or not h.isdigit():
                return ""
            utc_h = int(h)
            mm = int(m) if m.isdigit() else 0
            if src_tz in ("America/Bogota",):
                cot_h = utc_h
                utc_h_conv = (cot_h + 5) % 24
                return f"{cot_h:02d}:{mm:02d} COT ({utc_h_conv:02d}:{mm:02d} UTC)"
            else:
                cot_h = (utc_h - 5) % 24
                return f"{utc_h:02d}:{mm:02d} UTC ({cot_h:02d}:{mm:02d} COT)"

        if hour == "*":
            if "/" in minute:
                return f"Every {minute.split('/')[1]} min"
            elif minute.isdigit():
                return f"Hourly at :{minute.zfill(2)}"
            return expr

        if "," in hour:
            time_parts = []
            for h_part in hour.split(","):
                h_part = h_part.strip()
                if h_part.isdigit():
                    t = _fmt_time(h_part, minute, tz)
                    if t:
                        time_parts.append(t)
            if time_parts:
                return "Daily " + ", ".join(time_parts)

        time_str = _fmt_time(hour, minute, tz)

        if dom == "*" and month == "*" and dow == "*":
            freq = "Daily"
        elif dom == "*" and month == "*" and dow != "*":
            day_names = {
                "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
                "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun",
            }
            freq = f"Weekly {day_names.get(dow, dow)}"
        elif dom == "1" and month == "*":
            freq = "Monthly (1st)"
        else:
            freq = ""

        if time_str and freq:
            return f"{freq} {time_str}"
        elif time_str:
            return time_str
        return expr

    def _format_tasks(self, user_id: int) -> str:
        """Format scheduled tasks — zero LLM cost."""
        result = execute_list_scheduled_tasks()
        lines = ["**Scheduled Tasks**"]
        lines.append("=" * 28)

        # VPS Maintenance
        sys_cron = result.get("system_crontab", {})
        _maint_jobs = []
        for raw in sys_cron.get("jobs", []):
            clean = raw
            for prefix in ("[system] ", "[root] ", "[e2scrub_all] ", "[sysstat] "):
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                    break
            is_disabled = clean.startswith("#SENTINEL_DISABLED#")
            if is_disabled:
                clean = clean.replace("#SENTINEL_DISABLED#", "", 1).strip()
            cparts = clean.split(None, 5)
            if len(cparts) < 5:
                continue
            expr = " ".join(cparts[:5])
            cmd = cparts[5] if len(cparts) > 5 else ""
            if "cron.hourly" in cmd:
                name, desc = "system-hourly", "Run hourly scripts"
            elif "cron.daily" in cmd:
                name, desc = "system-daily", "Run daily scripts"
            elif "cron.weekly" in cmd:
                name, desc = "system-weekly", "Run weekly scripts"
            elif "cron.monthly" in cmd:
                name, desc = "system-monthly", "Run monthly scripts"
            elif "docker" in cmd and "prune" in cmd:
                name, desc = "docker-prune", "Clean old Docker build cache"
            elif "backup" in cmd.lower():
                name, desc = "openclaw-backup", "Backup OpenClaw config"
            elif "bak.*" in cmd and "delete" in cmd:
                name, desc = "log-cleanup", "Delete old log backups"
            elif "e2scrub" in cmd:
                name, desc = "disk-scrub", "Filesystem integrity check"
            elif "debian-sa1" in cmd:
                name, desc = "sysstat", "System activity data collection"
            else:
                name, desc = "cron-job", cmd[:50]
            status = " [OFF]" if is_disabled else " [ON]"
            sched = self._cron_to_human(expr)
            _maint_jobs.append((name, sched, desc, status))

        lines.append(f"\nVPS Maintenance ({len(_maint_jobs)} jobs)")
        for name, sched, desc, status in _maint_jobs:
            lines.append(f"  {name}{status}: {sched}")
            lines.append(f"    {desc}")

        # OpenClaw Cron
        oc_cron = result.get("openclaw_cron", {})
        oc_jobs = oc_cron.get("jobs", [])
        _OC_DESCRIPTIONS = {
            "news-brief-ai": "AI news digest \u2192 Discord #ai-brief (researcher)",
            "news-brief-enb": "Expert networks digest \u2192 Discord #enb (researcher)",
            "job-radar-am": "Morning job digest \u2192 Discord #job-radar (career)",
            "job-radar-pm": "Evening job digest \u2192 Discord #job-radar (career)",
            "competitor-intel-weekly": "Weekly competitor scan \u2192 Discord #enb (researcher)",
        }
        lines.append(f"\nOpenClaw Cron ({oc_cron.get('count', 0)} jobs)")
        for job in oc_jobs:
            name = job.get("name", "?")
            sched = job.get("schedule", "?")
            tz = job.get("tz", "UTC")
            enabled = job.get("enabled", True)
            desc = _OC_DESCRIPTIONS.get(name, job.get("description", ""))
            model = job.get("model", "")
            cmd = job.get("command", "")
            status = " [OFF]" if not enabled else " [ON]"
            human_sched = self._cron_to_human(sched, tz)
            lines.append(f"  {name}{status}: {human_sched}")
            if desc:
                lines.append(f"    {desc}")
            if cmd:
                model_short = model.split("/")[-1] if "/" in model else model
                lines.append(f"    cmd: {cmd} \u2014 model: {model_short}")
        if not oc_jobs:
            lines.append(f"  {oc_cron.get('note', 'None')}")

        # Job Radar
        jr = result.get("job_radar_scheduler", {})
        jr_jobs = jr.get("jobs", [])
        lines.append(f"\nJob Radar ({jr.get('count', 0)} jobs)")
        for job in jr_jobs:
            job_id = job.get("id", "?")
            sched_raw = job.get("schedule", "?")
            paused = job.get("paused", False)
            desc = job.get("desc", "")
            status = " [PAUSED]" if paused else " [ON]"
            human_sched = self._cron_to_human(sched_raw)
            lines.append(f"  {job_id}{status}: {human_sched}")
            if desc:
                lines.append(f"    {desc}")

        # Systemd Timers
        timers = result.get("systemd_timers", {})
        timer_count = timers.get("count", 0)
        lines.append(f"\nSystemd Timers: {timer_count} active (system managed)")

        self._set_zero_cost_stats(user_id)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _register_events(self) -> None:
        @self.bot.event
        async def on_ready():
            guild_id = self.config.discord_guild_id
            if guild_id:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("Discord slash commands synced to guild %s", guild_id)
            else:
                await self.tree.sync()
                logger.info("Discord slash commands synced globally")
            logger.info("Sentinel Discord bot ready as %s", self.bot.user)

        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore own messages
            if message.author == self.bot.user:
                return
            # Ignore other bots
            if message.author.bot:
                return
            # Auth check
            if not self._is_authorized(message.author.id):
                return
            # Only respond in the sentinel channel (if configured)
            if self.config.discord_channel_id and message.channel.id != self.config.discord_channel_id:
                return
            # Ignore slash commands (handled by tree)
            if message.content.startswith("/"):
                return

            user_message = message.content.strip()
            if not user_message:
                return

            logger.info("Discord message from %d: %s", message.author.id, user_message[:100])

            # Static responses (zero cost)
            static = self._check_static_response(user_message)
            if static:
                self._set_zero_cost_stats(message.author.id)
                response = self._append_usage_footer(message.author.id, static)
                await self._reply_chunked(message, response)
                return

            # LLM processing
            async with message.channel.typing():
                try:
                    response = await asyncio.to_thread(
                        self.agent.process_message, message.author.id, user_message
                    )
                    response = self._append_usage_footer(message.author.id, response)
                    await self._reply_chunked(message, response)
                except Exception as e:
                    logger.error("Error processing Discord message: %s", e, exc_info=True)
                    err_text = f"Error: {str(e)[:200]}"
                    err = self._append_usage_footer(message.author.id, err_text)
                    await self._reply_chunked(message, err)

    def _check_static_response(self, text: str) -> str | None:
        """Return static response for known greetings/queries, or None."""
        lower = text.lower().strip()
        provider, model = self._runtime_provider_model()
        provider_labels = {
            "openai": "OpenAI",
            "google": "Google Gemini",
            "anthropic": "Anthropic",
        }
        provider_label = provider_labels.get(provider, provider.title())
        statics = {
            "hi": "Sentinel online.",
            "hello": "Sentinel online.",
            "thanks": "No problem.",
            "ok": "Acknowledged.",
            "ping": "Pong.",
            "help": (
                "**Sentinel Commands**\n"
                "/status \u2014 System stats + containers\n"
                "/openclaw \u2014 Gateway health\n"
                "/security \u2014 Security audit\n"
                "/backup \u2014 Backup config\n"
                "/cost [today|week|month|all] \u2014 Cost dashboard\n"
                "/tasks \u2014 Scheduled tasks\n\n"
                "Or describe what you need in plain text."
            ),
            "what can you do": (
                "**Sentinel Capabilities**\n"
                "\u2022 System monitoring (CPU, RAM, disk)\n"
                "\u2022 Docker container management\n"
                "\u2022 Security auditing (UFW, SSH)\n"
                "\u2022 Config backup/restore\n"
                "\u2022 VPS cost tracking\n"
                "\u2022 Cron job management\n"
                "\u2022 OpenClaw health monitoring"
            ),
            "model": f"Sentinel runs on {model} via {provider_label}.",
            "codex": (
                f"OpenClaw uses GPT-5.3 Codex (subscription-covered). "
                f"Sentinel uses {model} via {provider_label}."
            ),
            "capabilities": (
                "**Sentinel Capabilities**\n"
                "\u2022 System monitoring (CPU, RAM, disk)\n"
                "\u2022 Docker container management\n"
                "\u2022 Security auditing (UFW, SSH)\n"
                "\u2022 Config backup/restore\n"
                "\u2022 VPS cost tracking\n"
                "\u2022 Cron job management\n"
                "\u2022 OpenClaw health monitoring"
            ),
        }
        return statics.get(lower)

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    def _register_commands(self) -> None:
        @self.tree.command(name="status", description="System stats + container health")
        async def status_cmd(interaction: discord.Interaction):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            if not self._is_sentinel_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Sentinel commands only work in <#{}>.".format(self.config.discord_channel_id),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            try:
                response = self._format_static_stats(interaction.user.id)
            except Exception as e:
                logger.error("Discord /status failed: %s", e, exc_info=True)
                response = f"Error getting status: {str(e)[:200]}"
            response = self._append_usage_footer(interaction.user.id, response)
            await self._reply_chunked(interaction, response)

        @self.tree.command(name="openclaw", description="OpenClaw gateway health")
        async def openclaw_cmd(interaction: discord.Interaction):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            if not self._is_sentinel_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Sentinel commands only work in <#{}>.".format(self.config.discord_channel_id),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            try:
                result = execute_check_openclaw_health()
                lines = ["**OpenClaw Health**"]
                lines.append(f"Container: {result.get('status', '?')}")
                health_badge = "\u2705" if result.get("gateway_ready") else "\u26a0\ufe0f"
                lines.append(f"Health: {health_badge} {result.get('docker_health', '?')}")
                lines.append(f"Uptime: {result.get('uptime', '?')}")
                lines.append(f"HTTP: {result.get('http_probe_status', '?')}")
                errors = result.get("recent_errors", [])
                if errors:
                    lines.append(f"\n**Recent Errors ({len(errors)}):**")
                    for e in errors[:5]:
                        lines.append(f"\u2022 {str(e)[:120]}")
                else:
                    lines.append("No recent errors.")
                response = "\n".join(lines)
            except Exception as e:
                logger.error("Discord /openclaw failed: %s", e, exc_info=True)
                response = f"Error checking OpenClaw: {str(e)[:200]}"
            self._set_zero_cost_stats(interaction.user.id)
            response = self._append_usage_footer(interaction.user.id, response)
            await self._reply_chunked(interaction, response)

        @self.tree.command(name="security", description="Security audit (UFW, fail2ban, ports)")
        async def security_cmd(interaction: discord.Interaction):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            if not self._is_sentinel_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Sentinel commands only work in <#{}>.".format(self.config.discord_channel_id),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            try:
                result = execute_check_security()
                lines = ["**Security Audit**"]
                for section in ["ufw", "listening_ports", "failed_ssh_attempts", "running_services_count"]:
                    val = result.get(section, "N/A")
                    label = section.replace("_", " ").title()
                    if isinstance(val, list):
                        lines.append(f"\n**{label}:**")
                        for item in val[:10]:
                            lines.append(f"\u2022 {str(item)[:120]}")
                    else:
                        lines.append(f"{label}: {str(val)[:200]}")
                response = "\n".join(lines)
            except Exception as e:
                logger.error("Discord /security failed: %s", e, exc_info=True)
                response = f"Error running security audit: {str(e)[:200]}"
            self._set_zero_cost_stats(interaction.user.id)
            response = self._append_usage_footer(interaction.user.id, response)
            await self._reply_chunked(interaction, response)

        @self.tree.command(name="backup", description="Backup OpenClaw config + workspace")
        async def backup_cmd(interaction: discord.Interaction):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            if not self._is_sentinel_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Sentinel commands only work in <#{}>.".format(self.config.discord_channel_id),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            try:
                result = execute_backup_openclaw()
                if result.get("status") == "success":
                    response = (
                        f"**Backup Complete**\n"
                        f"File: `{result.get('path', '?')}`\n"
                        f"Size: {result.get('size_mb', 0):.1f} MB"
                    )
                else:
                    response = f"Backup failed: {str(result.get('error', 'unknown'))[:200]}"
            except Exception as e:
                logger.error("Discord /backup failed: %s", e, exc_info=True)
                response = f"Error creating backup: {str(e)[:200]}"
            self._set_zero_cost_stats(interaction.user.id)
            response = self._append_usage_footer(interaction.user.id, response)
            await self._reply_chunked(interaction, response)

        @self.tree.command(name="cost", description="VPS cost dashboard (today/week/month/all)")
        @app_commands.describe(period="Time period: today, week, month, or all")
        async def cost_cmd(interaction: discord.Interaction, period: str = "today"):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            if not self._is_sentinel_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Sentinel commands only work in <#{}>.".format(self.config.discord_channel_id),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            try:
                cleaned = period.lower().strip()
                if cleaned not in _COST_PERIODS:
                    cleaned = "today"
                result = execute_cost_summary(cleaned)
                response = self._format_cost_dashboard(result)
            except Exception as e:
                logger.error("Discord /cost failed: %s", e, exc_info=True)
                response = f"Error getting cost summary: {str(e)[:200]}"
            self._set_zero_cost_stats(interaction.user.id)
            response = self._append_usage_footer(interaction.user.id, response)
            await self._reply_chunked(interaction, response)

        @self.tree.command(name="tasks", description="Scheduled tasks + cron status")
        async def tasks_cmd(interaction: discord.Interaction):
            if not self._is_authorized(interaction.user.id):
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            if not self._is_sentinel_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Sentinel commands only work in <#{}>.".format(self.config.discord_channel_id),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            try:
                response = self._format_tasks(interaction.user.id)
            except Exception as e:
                logger.error("Discord /tasks failed: %s", e, exc_info=True)
                response = f"Error listing tasks: {str(e)[:200]}"
            response = self._append_usage_footer(interaction.user.id, response)
            await self._reply_chunked(interaction, response)

    # ------------------------------------------------------------------
    # Bot runner
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the Discord bot (blocking)."""
        logger.info("Sentinel Discord bot starting...")
        self.bot.run(self.config.discord_token, log_handler=None)
