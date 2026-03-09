"""Sentinel: Sysadmin bot for OpenClaw VPS management.

Supports Anthropic and Google Gemini providers with the same tool-execution loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - dependency may be unavailable in local test envs
    Anthropic = None

from config import SentinelConfig
from cost_tracker import APICostTracker
from tools import GOOGLE_TOOLS, TOOLS, execute_tool, set_cost_tracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
# Keep third-party client logs from leaking tokenized request URLs into journals.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("sentinel")

SYSTEM_PROMPT = """\
<role>
Sentinel — sysadmin of Hetzner CPX22 VPS (Ubuntu 24.04).
You manage infrastructure. OpenClaw (Docker, Codex model) handles AI tasks.
You run on Gemini Flash — cheapest viable model ($0.30/$2.50 per 1M tokens).
</role>

<rules>
- NEVER ask clarification questions. Execute with reasonable defaults.
- Execute restarts immediately when requested. Only confirm data deletion.
- Maximum 8 bullet points per response. No prose paragraphs.
- Never list your capabilities unless user explicitly asks "what can you do".
- If gateway is down, report it and offer to restart — don't just report status.
- Use ONLY provided tools. Never suggest manual SSH commands.
- Never expose secrets, tokens, or API keys.
- If a tool fails, retry once before reporting failure.
</rules>

<environment>
- Containers: openclaw-openclaw-gateway-1, job-radar-agent, job-radar-db
- Channels: Telegram (Sentinel + cron delivery), Discord (OpenClaw ACP threads)
- OpenClaw: Codex model (subscription), Flash fallback. Hooks: session-memory, command-logger
- Cron: AI brief 07:10 COT, ENB brief 07:00 COT (isolated, announce to Telegram)
- Heartbeat: 180m interval, 07:00-23:00 COT, target=last
- Anti-spiral: loopDetection (warn@10/critical@20/breaker@30), on-failure:5, SOUL.md budgets
- Session: daily reset 04:00, enforce maintenance, Gemini embeddings memory search
- Firewall: UFW (SSH only), fail2ban
- Cost: exact JSONL (Sentinel), estimated Docker logs (OpenClaw/JR). Codex=$0.
</environment>

<output_format>
- Bullet points for status. Code blocks for logs.
- One summary line at end for multi-step results.
</output_format>
"""


class SentinelAgent:
    """Provider-backed sysadmin agent with tool use."""

    def __init__(self, config: SentinelConfig):
        self.config = config
        self.provider = config.provider

        self.client: Any
        self.anthropic_client: Any | None = None
        self.google_module: Any | None = None
        self.google_client: Any | None = None

        if Anthropic is not None and config.anthropic_api_key:
            self.anthropic_client = Anthropic(api_key=config.anthropic_api_key)
        elif self.provider == "anthropic":
            if Anthropic is None:
                raise RuntimeError(
                    "SENTINEL_PROVIDER=anthropic requires the anthropic package. "
                    "Install dependencies from sentinel/requirements.txt"
                )
            raise RuntimeError("SENTINEL_PROVIDER=anthropic requires ANTHROPIC_API_KEY")

        if config.google_api_key:
            try:
                self.google_module, self.google_client = self._init_google_client()
            except Exception:
                if self.provider == "google":
                    raise
                logger.exception("Google fallback initialization failed; continuing without fallback")
        elif self.provider == "google":
            raise RuntimeError("SENTINEL_PROVIDER=google requires GEMINI_API_KEY")

        if self.provider == "anthropic":
            self.client = self.anthropic_client
        elif self.provider == "google":
            self.client = self.google_client
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        if self.client is None:
            raise RuntimeError(f"Configured provider '{self.provider}' could not be initialized")

        self.conversations: dict[int, list[dict[str, Any]]] = {}
        self._last_activity: dict[int, float] = {}
        self._request_windows: dict[int, deque[float]] = {}
        self._last_request_stats: dict[int, dict[str, Any]] = {}
        self._state_lock = threading.Lock()

        self._audit_log_path = Path(self.config.audit_log_file)
        self._audit_prev_hash = ""
        self._prepare_audit_log()
        self._configure_file_logging()
        self._cost_tracker: APICostTracker | None = None
        if self.config.cost_tracking_enabled:
            try:
                self._cost_tracker = APICostTracker(
                    usage_log_file=self.config.api_usage_log_file,
                    summary_file=self.config.api_cost_summary_file,
                    retention_days=self.config.cost_retention_days,
                )
                set_cost_tracker(self._cost_tracker)
            except Exception:
                logger.exception("Failed to initialize API cost tracker; continuing without cost tracking")

    @staticmethod
    def _normalize_google_model_name(raw_model: str) -> str:
        """Normalize aliases and provider-prefixed model ids for Gemini calls."""
        model = (raw_model or "").strip()
        alias_map = {
            "flash": "gemini-2.5-flash",
            "gemini-flash": "gemini-2.5-flash",
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-pro": "gemini-2.5-pro",
            "pro": "gemini-2.5-pro",
            "gemini-2.5-pro": "gemini-2.5-pro",
        }
        if model in alias_map:
            return alias_map[model]
        if model.startswith("google/"):
            return model.split("/", 1)[1]
        if "haiku" in model:
            return "gemini-2.5-flash"
        if "sonnet" in model or "opus" in model:
            return "gemini-2.5-pro"
        return model or "gemini-2.5-flash"

    @staticmethod
    def _normalize_anthropic_model_name(raw_model: str) -> str:
        """Normalize aliases/provider-prefixed model ids for Anthropic calls.

        Policy: Haiku is NEVER used. Default Anthropic model is Sonnet 4.6.
        Anthropic is only for explicit manual provider override, not auto-fallback.
        """
        model = (raw_model or "").strip()
        alias_map = {
            "haiku": "claude-sonnet-4-6",
            "claude-haiku-4-5": "claude-sonnet-4-6",
            "claude-haiku-4-6": "claude-sonnet-4-6",
            "sonnet": "claude-sonnet-4-6",
            "claude-sonnet-4-5": "claude-sonnet-4-6",
            "claude-sonnet-4-6": "claude-sonnet-4-6",
            "opus": "claude-opus-4-6",
            "claude-opus-4-6": "claude-opus-4-6",
        }
        if model in alias_map:
            return alias_map[model]
        if model.startswith("anthropic/"):
            stripped = model.split("/", 1)[1]
            return alias_map.get(stripped, stripped)
        if model.startswith("google/") or "gemini" in model:
            return "claude-sonnet-4-6"
        return model or "claude-sonnet-4-6"

    def _resolve_model_for_provider(self, provider: str) -> str:
        """Select a model id valid for the target provider."""
        if provider == "google":
            return self._normalize_google_model_name(self.config.model)
        if provider == "anthropic":
            return self._normalize_anthropic_model_name(self.config.model)
        return self.config.model

    def _init_google_client(self) -> tuple[Any, Any]:
        """Initialize Gemini client lazily so Anthropic-only environments still run."""
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError(
                "SENTINEL_PROVIDER=google requires google-generativeai. "
                "Install dependencies from sentinel/requirements.txt"
            ) from exc

        genai.configure(api_key=self.config.google_api_key)
        model_name = self._normalize_google_model_name(self.config.model)
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        return genai, model

    def _configure_file_logging(self) -> None:
        """Persist operational logs to disk when writable."""
        log_path = Path(self.config.log_file)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if not any(
                isinstance(h, logging.FileHandler)
                and getattr(h, "baseFilename", None) == str(log_path)
                for h in logger.handlers
            ):
                handler = logging.FileHandler(log_path)
                handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
                logger.addHandler(handler)
        except OSError as exc:
            logger.warning("Could not configure file logging at %s: %s", log_path, exc)

    def _prepare_audit_log(self) -> None:
        """Create audit file and load previous hash for hash-chain integrity."""
        try:
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            if not self._audit_log_path.exists():
                self._audit_log_path.touch(mode=0o640)
            self._audit_prev_hash = self._load_previous_audit_hash()
        except OSError as exc:
            logger.warning("Audit log unavailable (%s): %s", self._audit_log_path, exc)
            self._audit_prev_hash = ""

    def _load_previous_audit_hash(self) -> str:
        """Read the hash from the most recent valid audit entry."""
        try:
            lines = self._audit_log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                event_hash = event.get("entry_hash")
                if isinstance(event_hash, str):
                    return event_hash
        return ""

    def _append_audit_event(self, user_id: int, event_type: str, payload: dict[str, Any]) -> None:
        """Write a hash-chained audit event to persistent storage."""
        if not self._audit_log_path:
            return
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user_id": user_id,
            "event": event_type,
            "payload": payload,
            "prev_hash": self._audit_prev_hash,
        }
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event["entry_hash"] = event_hash

        try:
            with self._audit_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._audit_prev_hash = event_hash
        except OSError as exc:
            logger.warning("Failed to append audit event: %s", exc)

    @staticmethod
    def _new_request_stats() -> dict[str, Any]:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_usd": 0.0,
            "calls": 0,
            "error_calls": 0,
            "providers": [],
            "models": [],
            "brave_api_calls": 0,
            "status": "started",
        }

    def _store_last_request_stats(self, user_id: int, stats: dict[str, Any]) -> None:
        snapshot = {
            "input_tokens": int(stats.get("input_tokens", 0)),
            "output_tokens": int(stats.get("output_tokens", 0)),
            "estimated_usd": round(float(stats.get("estimated_usd", 0.0)), 8),
            "calls": int(stats.get("calls", 0)),
            "error_calls": int(stats.get("error_calls", 0)),
            "providers": list(stats.get("providers", [])),
            "models": list(stats.get("models", [])),
            "brave_api_calls": int(stats.get("brave_api_calls", 0)),
            "status": str(stats.get("status", "unknown")),
        }
        with self._state_lock:
            self._last_request_stats[user_id] = snapshot

    def get_last_request_stats(self, user_id: int) -> dict[str, Any]:
        with self._state_lock:
            stats = self._last_request_stats.get(user_id)
            if not isinstance(stats, dict):
                return self._new_request_stats()
            return dict(stats)

    @staticmethod
    def _try_static_response(user_message: str, provider: str, model: str) -> str | None:
        """Handle trivial low-information prompts without an LLM call."""
        normalized = " ".join((user_message or "").strip().lower().split())
        if not normalized:
            return "Please send a command or question."
        if normalized in {"hi", "hello", "hey", "hola", "buenas"}:
            return "Hello. How can I help?"
        if normalized in {"thanks", "thank you", "thx", "gracias", "ty"}:
            return "Standing by."
        if normalized in {"ok", "okay", "got it", "understood", "k"}:
            return "Standing by."
        if normalized in {"help", "?"}:
            return (
                "Commands: /status, /openclaw, /security, /backup, "
                "/cost [today|week|month|all], /tasks — or describe what you need."
            )
        if normalized == "ping":
            return "Pong."
        if normalized in {"status", "system status", "check status", "server status"}:
            return "Use /status for system stats + container health."
        if normalized in {"tasks", "cron", "cron jobs", "scheduled tasks", "jobs"}:
            return "Use /tasks to see all scheduled tasks and their status."
        if normalized in {"cost", "costs", "how much", "spending", "budget"}:
            return "Use /cost [today|week|month|all] for the VPS cost dashboard."
        if normalized in {"backup", "backups"}:
            return "Use /backup to backup OpenClaw config + workspace."
        if any(
            token in normalized
            for token in (
                "what model",
                "which model",
                "what's your model",
                "whats your model",
                "run on gemini",
                "model of llm",
            )
        ):
            return f"Primary model: {model} (provider: {provider})."
        # Architecture / Codex queries
        if any(
            token in normalized
            for token in (
                "not codex",
                "why not codex",
                "use codex",
                "why gemini",
                "why flash",
                "why not openai",
                "switch to codex",
                "codex sdk",
            )
        ):
            return (
                f"Sentinel uses {model} — cheapest viable model "
                f"($0.30/$2.50 per 1M tokens). "
                f"OpenClaw uses Codex (subscription-covered, $0). "
                f"Different tools, different models."
            )
        # Capability queries (keyword-based)
        if any(
            token in normalized
            for token in (
                "what can you do",
                "capabilities",
                "your tools",
                "what tools",
                "list tools",
                "your functions",
            )
        ):
            return (
                "I can: monitor system health, manage Docker containers, "
                "check security, create backups, track costs, detect API spirals, "
                "list scheduled tasks, and manage cron jobs (enable/disable). "
                "Commands: /status /openclaw /security /backup /cost /tasks"
            )
        return None

    def _enforce_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """Apply per-user sliding-window rate limit."""
        now = time.monotonic()
        with self._state_lock:
            window = self._request_windows.setdefault(user_id, deque())
            while window and (now - window[0]) > self.config.rate_limit_window_seconds:
                window.popleft()

            if len(window) >= self.config.rate_limit_max_requests:
                retry_after = max(
                    1,
                    int(self.config.rate_limit_window_seconds - (now - window[0])),
                )
                return False, retry_after

            window.append(now)
            return True, 0

    def _cleanup_stale_users(self, now: float) -> None:
        """Remove per-user state for users inactive longer than 2x conversation TTL.

        Prevents unbounded dict growth across conversations, _last_activity,
        _request_windows, and _last_request_stats.
        MUST be called while self._state_lock is held.
        """
        stale_threshold = self.config.conversation_ttl_seconds * 2
        stale_ids = [
            uid for uid, last_seen in self._last_activity.items()
            if (now - last_seen) > stale_threshold
        ]
        for uid in stale_ids:
            self.conversations.pop(uid, None)
            self._last_activity.pop(uid, None)
            self._request_windows.pop(uid, None)
            self._last_request_stats.pop(uid, None)
        if stale_ids:
            logger.debug("Cleaned up state for %d stale user(s)", len(stale_ids))

    def _prepare_history(self, user_id: int) -> list[dict[str, Any]]:
        """Get mutable message history and expire stale sessions."""
        now = time.monotonic()
        with self._state_lock:
            self._cleanup_stale_users(now)

            last_seen = self._last_activity.get(user_id)
            if last_seen is not None and (now - last_seen) > self.config.conversation_ttl_seconds:
                self.conversations[user_id] = []
                self._append_audit_event(
                    user_id,
                    "conversation_reset",
                    {"reason": "ttl_expired", "ttl_seconds": self.config.conversation_ttl_seconds},
                )

            history = self.conversations.setdefault(user_id, [])
            self._last_activity[user_id] = now
            return history

    @staticmethod
    def _serialize_tool_result(result: Any) -> tuple[str, bool]:
        """Serialize tool result safely and mark truncation explicitly."""
        try:
            raw = json.dumps(result, ensure_ascii=False)
        except TypeError as exc:
            fallback = {
                "serialization_error": str(exc),
                "result_type": type(result).__name__,
                "result_repr": repr(result)[:500],
            }
            raw = json.dumps(fallback, ensure_ascii=False)

        if len(raw) <= 2000:
            return raw, False

        truncated = {
            "truncated": True,
            "original_length": len(raw),
            "preview": raw[:1500],
        }
        return json.dumps(truncated, ensure_ascii=False), True

    @staticmethod
    def _coerce_mapping(value: Any) -> dict[str, Any]:
        """Best-effort conversion of SDK map-like objects to plain dicts."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            converted = value.to_dict()
            if isinstance(converted, dict):
                return converted
        if hasattr(value, "items"):
            try:
                return dict(value.items())
            except Exception:  # pragma: no cover - defensive for SDK internals
                pass
        if isinstance(value, (str, bytes, int, float, bool)):
            return {"value": value}
        try:
            converted = json.loads(json.dumps(value))
            return converted if isinstance(converted, dict) else {"value": converted}
        except Exception:  # pragma: no cover - defensive for SDK internals
            return {"value": str(value)}

    @staticmethod
    def _truncate_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the latest conversation window while preserving structural integrity.

        Gemini requires strict alternation: user → model → user (function_response) → model.
        Naive truncation can break this by cutting in the middle of a tool-call pair.
        """
        if len(history) <= 20:
            return history

        truncated = history[-20:]

        # Strip orphaned turns from the start until we have a clean user turn.
        while truncated:
            first = truncated[0]
            role = first.get("role", "")
            parts = first.get("parts", [])

            # Remove orphaned function_response at start (missing preceding function_call)
            if role == "user" and parts and any(
                isinstance(p, dict) and "function_response" in p for p in parts
            ):
                truncated = truncated[1:]
                continue

            # Must start with a user turn for Gemini
            if role == "model":
                truncated = truncated[1:]
                continue

            break

        # Remove dangling function_call at end (model turn with function_calls but no response)
        while truncated:
            last = truncated[-1]
            last_parts = last.get("parts", [])
            if (
                last.get("role") == "model"
                and last_parts
                and any(isinstance(p, dict) and "function_call" in p for p in last_parts)
            ):
                truncated.pop()
                continue
            break

        return truncated if len(truncated) >= 1 else history[-2:]

    @staticmethod
    def _sanitize_google_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate and fix Gemini history to prevent 400 errors.

        Enforces:
        1. Starts with a user turn (not function_response)
        2. function_response immediately follows a model turn with function_call
        3. No consecutive model turns
        """
        if not history:
            return history

        sanitized: list[dict[str, Any]] = []

        for turn in history:
            role = turn.get("role", "")
            parts = turn.get("parts", [])

            if not parts:
                continue

            is_fn_response = (
                role == "user"
                and any(isinstance(p, dict) and "function_response" in p for p in parts)
            )

            if is_fn_response:
                # Must follow a model turn with function_call
                if not sanitized:
                    continue
                prev = sanitized[-1]
                prev_parts = prev.get("parts", [])
                has_fn_call = (
                    prev.get("role") == "model"
                    and any(isinstance(p, dict) and "function_call" in p for p in prev_parts)
                )
                if not has_fn_call:
                    continue
                sanitized.append(turn)
                continue

            # Prevent consecutive model turns
            if role == "model" and sanitized and sanitized[-1].get("role") == "model":
                sanitized[-1] = turn
                continue

            sanitized.append(turn)

        # Strip dangling function_call at end
        while sanitized:
            last = sanitized[-1]
            last_parts = last.get("parts", [])
            if (
                last.get("role") == "model"
                and last_parts
                and any(isinstance(p, dict) and "function_call" in p for p in last_parts)
            ):
                sanitized.pop()
            else:
                break

        # Must start with user turn
        while sanitized and sanitized[0].get("role") != "user":
            sanitized.pop(0)

        return sanitized if sanitized else history[-2:]

    def _persist_history(self, user_id: int, history: list[dict[str, Any]]) -> None:
        """Thread-safe persistence of truncated conversation history."""
        with self._state_lock:
            self.conversations[user_id] = self._truncate_history(history)

    def _record_api_usage(
        self,
        *,
        provider: str,
        model: str,
        status: str,
        user_id: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: Exception | None = None,
        request_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        event: dict[str, Any] | None = None
        error_type = type(error).__name__ if error else None
        error_preview = str(error) if error else None
        if self._cost_tracker is not None:
            try:
                event = self._cost_tracker.record(
                    provider=provider,
                    model=model,
                    status=status,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    user_id=user_id,
                    error_type=error_type,
                    error_preview=error_preview,
                )
            except Exception:
                logger.exception("API cost tracking failed")

        if request_stats is not None:
            request_stats["input_tokens"] = int(request_stats.get("input_tokens", 0)) + max(0, int(input_tokens))
            request_stats["output_tokens"] = int(request_stats.get("output_tokens", 0)) + max(0, int(output_tokens))
            request_stats["calls"] = int(request_stats.get("calls", 0)) + 1
            if status != "success":
                request_stats["error_calls"] = int(request_stats.get("error_calls", 0)) + 1
            if event is not None:
                request_stats["estimated_usd"] = round(
                    float(request_stats.get("estimated_usd", 0.0)) + float(event.get("estimated_usd", 0.0)),
                    8,
                )
            providers = request_stats.setdefault("providers", [])
            if provider not in providers:
                providers.append(provider)
            models = request_stats.setdefault("models", [])
            if model not in models:
                models.append(model)
        return event

    @staticmethod
    def _mark_brave_usage(tool_name: str, tool_input: dict[str, Any], request_stats: dict[str, Any] | None) -> None:
        if request_stats is None:
            return
        payload = json.dumps({"name": tool_name, "input": tool_input}, ensure_ascii=False).lower()
        if "brave" in payload or "api.search.brave.com" in payload:
            request_stats["brave_api_calls"] = int(request_stats.get("brave_api_calls", 0)) + 1

    def _extract_anthropic_usage(self, response: Any) -> tuple[int, int]:
        usage = self._coerce_mapping(getattr(response, "usage", None))
        input_tokens = int(usage.get("input_tokens") or usage.get("inputTokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("outputTokens") or 0)
        return max(input_tokens, 0), max(output_tokens, 0)

    def _extract_google_usage(self, response: Any) -> tuple[int, int]:
        """Extract token counts from Gemini proto objects via direct attribute access."""
        usage_obj = getattr(response, "usage_metadata", None)
        if usage_obj is None:
            usage_obj = getattr(response, "usageMetadata", None)
        if usage_obj is None:
            logger.debug(
                "Gemini response has no usage_metadata; token counts unavailable "
                "(response type: %s, has candidates: %s)",
                type(response).__name__,
                bool(getattr(response, "candidates", None)),
            )
            return 0, 0
        # Proto objects expose fields as attributes, NOT dict keys
        input_tokens = int(
            getattr(usage_obj, "prompt_token_count", 0)
            or getattr(usage_obj, "promptTokenCount", 0)
            or 0
        )
        output_tokens = int(
            getattr(usage_obj, "candidates_token_count", 0)
            or getattr(usage_obj, "candidatesTokenCount", 0)
            or 0
        )
        if output_tokens == 0:
            total_tokens = int(
                getattr(usage_obj, "total_token_count", 0)
                or getattr(usage_obj, "totalTokenCount", 0)
                or 0
            )
            if total_tokens > 0 and input_tokens > 0:
                output_tokens = max(0, total_tokens - input_tokens)
        return max(input_tokens, 0), max(output_tokens, 0)

    def _call_anthropic(self, history: list[dict[str, Any]], model_name: str) -> Any:
        if self.anthropic_client is None:
            raise RuntimeError("Anthropic client is not initialized")
        return self.anthropic_client.messages.create(
            model=model_name,
            max_tokens=self.config.max_tokens,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
            timeout=60.0,
        )

    def _call_google(self, history: list[dict[str, Any]], client: Any | None = None) -> Any:
        active_client = client or self.google_client
        if active_client is None:
            raise RuntimeError("Google client is not initialized")
        # Sanitize history to prevent Gemini 400 errors from malformed turn ordering.
        safe_history = self._sanitize_google_history(history)
        return active_client.generate_content(
            safe_history,
            tools=GOOGLE_TOOLS,
            generation_config={
                "max_output_tokens": self.config.max_tokens,
                "temperature": 0.2,  # Low: sysadmin tasks need deterministic, factual output
            },
            request_options={"timeout": 60},
        )

    def _extract_google_response(
        self,
        response: Any,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Extract text and function-calls from a Gemini response."""
        text_chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        assistant_parts: list[dict[str, Any]] = []

        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            role = getattr(content, "role", "model") if content is not None else "model"
            parts = getattr(content, "parts", None) or []
        else:
            role = "model"
            parts = []

        for part in parts:
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                name = getattr(function_call, "name", None)
                args_raw = getattr(function_call, "args", None)
                args = self._coerce_mapping(args_raw)
                if name:
                    tool_calls.append({"name": name, "input": args})
                    assistant_parts.append({"function_call": {"name": name, "args": args}})
                continue

            text = getattr(part, "text", None)
            if text:
                text_chunks.append(text)
                assistant_parts.append({"text": text})

        # SDK fallbacks: some responses expose only response.text even when
        # candidate parts are sparse/empty.
        if not text_chunks:
            direct_text = ""
            try:
                raw_direct_text = getattr(response, "text", None)
                if isinstance(raw_direct_text, str):
                    direct_text = raw_direct_text.strip()
            except Exception:  # pragma: no cover - defensive for SDK behavior
                direct_text = ""
            if direct_text:
                text_chunks.append(direct_text)
                assistant_parts.append({"text": direct_text})

        if not assistant_parts:
            assistant_parts = [{"text": ""}]

        assistant_turn = {"role": role or "model", "parts": assistant_parts}
        return "".join(text_chunks).strip(), tool_calls, assistant_turn

    def _run_anthropic_loop(
        self,
        user_id: int,
        history: list[dict[str, Any]],
        persist_history: bool = True,
        model_name: str | None = None,
        request_stats: dict[str, Any] | None = None,
    ) -> str:
        """Run Anthropic tool-use loop until a final text response is produced."""
        active_model = model_name or self._resolve_model_for_provider("anthropic")
        for _ in range(self.config.max_tool_iterations):
            try:
                response = self._call_anthropic(history, model_name=active_model)
            except Exception as exc:
                self._record_api_usage(
                    provider="anthropic",
                    model=active_model,
                    status="error",
                    user_id=user_id,
                    error=exc,
                    request_stats=request_stats,
                )
                raise

            input_tokens, output_tokens = self._extract_anthropic_usage(response)
            self._record_api_usage(
                provider="anthropic",
                model=active_model,
                status="success",
                user_id=user_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_stats=request_stats,
            )

            if response.stop_reason == "tool_use":
                assistant_content = response.content
                history.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type != "tool_use":
                        continue
                    logger.info("Executing tool: %s(%s)", block.name, json.dumps(block.input)[:200])
                    self._mark_brave_usage(block.name, block.input, request_stats)
                    result = execute_tool(block.name, block.input)
                    serialized, truncated = self._serialize_tool_result(result)
                    self._append_audit_event(
                        user_id,
                        "tool_execution",
                        {
                            "tool_name": block.name,
                            "tool_input": block.input,
                            "result_truncated": truncated,
                            "result_chars": len(serialized),
                        },
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": serialized,
                        }
                    )

                history.append({"role": "user", "content": tool_results})
                continue

            text_response = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text_response += block.text

            history.append({"role": "assistant", "content": response.content})
            if persist_history:
                self._persist_history(user_id, history)
            self._append_audit_event(
                user_id,
                "assistant_response",
                {"chars": len(text_response), "preview": text_response[:200]},
            )
            return text_response

        self._append_audit_event(
            user_id,
            "max_iterations_reached",
            {"limit": self.config.max_tool_iterations},
        )
        return "Reached maximum tool iterations. Something may be stuck. Please try again."

    def _run_google_loop(
        self,
        user_id: int,
        history: list[dict[str, Any]],
        client: Any | None = None,
        persist_history: bool = True,
        model_name: str | None = None,
        request_stats: dict[str, Any] | None = None,
    ) -> str:
        """Run Gemini function-calling loop until a final text response is produced."""
        latest_tool_result = ""
        blank_response_retries = 0
        google_model = model_name or self._resolve_model_for_provider("google")
        for _ in range(self.config.max_tool_iterations):
            try:
                response = self._call_google(history, client=client)
            except Exception as exc:
                self._record_api_usage(
                    provider="google",
                    model=google_model,
                    status="error",
                    user_id=user_id,
                    error=exc,
                    request_stats=request_stats,
                )
                raise

            input_tokens, output_tokens = self._extract_google_usage(response)
            self._record_api_usage(
                provider="google",
                model=google_model,
                status="success",
                user_id=user_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_stats=request_stats,
            )

            text_response, tool_calls, assistant_turn = self._extract_google_response(response)
            history.append(assistant_turn)

            if tool_calls:
                function_responses = []
                for call in tool_calls:
                    tool_name = call["name"]
                    tool_input = call.get("input", {})
                    logger.info("Executing tool: %s(%s)", tool_name, json.dumps(tool_input)[:200])
                    self._mark_brave_usage(tool_name, tool_input, request_stats)
                    result = execute_tool(tool_name, tool_input)
                    serialized, truncated = self._serialize_tool_result(result)
                    latest_tool_result = serialized
                    self._append_audit_event(
                        user_id,
                        "tool_execution",
                        {
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                            "result_truncated": truncated,
                            "result_chars": len(serialized),
                        },
                    )
                    function_responses.append(
                        {
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": serialized},
                            }
                        }
                    )

                history.append({"role": "user", "parts": function_responses})
                history = self._truncate_history(history)
                if persist_history:
                    self._persist_history(user_id, history)
                continue

            if text_response:
                final_text = text_response
            elif latest_tool_result:
                final_text = (
                    "Tool execution completed; model returned no narrative summary. "
                    f"Latest tool result: {latest_tool_result[:600]}"
                )
            else:
                if blank_response_retries < 1:
                    blank_response_retries += 1
                    history.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": (
                                        "Provide a concise plain-text answer to the previous user request. "
                                        "Do not call tools unless strictly required."
                                    )
                                }
                            ],
                        }
                    )
                    history = self._truncate_history(history)
                    if persist_history:
                        self._persist_history(user_id, history)
                    continue
                final_text = "Gemini returned an empty response. Please retry your request."
            history = self._truncate_history(history)
            if persist_history:
                self._persist_history(user_id, history)
            self._append_audit_event(
                user_id,
                "assistant_response",
                {"chars": len(final_text), "preview": final_text[:200]},
            )
            return final_text

        self._append_audit_event(
            user_id,
            "max_iterations_reached",
            {"limit": self.config.max_tool_iterations},
        )
        return "Reached maximum tool iterations. Something may be stuck. Please try again."

    @staticmethod
    def _is_history_corruption_error(exc: Exception) -> bool:
        """Detect Gemini 400 errors caused by malformed conversation history.

        These are recoverable by clearing the conversation and retrying.
        """
        details = f"{type(exc).__name__}: {exc}".lower()
        markers = (
            "function call turn",
            "function_response",
            "please ensure",
            "invalid argument",
        )
        is_400 = "400" in details
        has_marker = any(m in details for m in markers)
        return is_400 and has_marker

    @staticmethod
    def _is_recoverable_provider_error(exc: Exception) -> bool:
        """Detect provider errors that deserve a friendly message instead of a raw traceback."""
        details = f"{type(exc).__name__}: {exc}".lower()
        markers = (
            "authentication_error",
            "invalid x-api-key",
            "status code: 401",
            "status code: 429",
            "status code: 503",
            "status code: 529",
            "rate limit",
            "overload",
            "timeout",
            "connection",
            "temporarily unavailable",
        )
        return any(marker in details for marker in markers)

    @staticmethod
    def _is_soft_google_response_error(exc: Exception) -> bool:
        """Return True for non-provider outages where Gemini returned no usable text."""
        details = f"{type(exc).__name__}: {exc}".lower()
        return "google_empty_response" in details or "empty_response" in details

    def _process_with_provider(
        self,
        provider: str,
        user_id: int,
        user_message: str,
        *,
        persist_history: bool,
        use_existing_history: bool,
        request_stats: dict[str, Any] | None = None,
    ) -> str:
        base_history = self._prepare_history(user_id) if use_existing_history else []
        history = list(base_history)

        if provider == "google":
            history.append({"role": "user", "parts": [{"text": user_message}]})
        else:
            history.append({"role": "user", "content": user_message})

        self._append_audit_event(
            user_id,
            "user_message",
            {
                "provider": provider,
                "chars": len(user_message),
                "preview": user_message[:200],
            },
        )

        history = self._truncate_history(history)

        if provider == "google":
            model_name = self._resolve_model_for_provider("google")
            return self._run_google_loop(
                user_id,
                history,
                client=self.google_client,
                persist_history=persist_history,
                model_name=model_name,
                request_stats=request_stats,
            )
        model_name = self._resolve_model_for_provider("anthropic")
        return self._run_anthropic_loop(
            user_id,
            history,
            persist_history=persist_history,
            model_name=model_name,
            request_stats=request_stats,
        )

    def process_message(self, user_id: int, user_message: str) -> str:
        """Process a user message through the configured provider with tool use.

        Implements the agentic loop: send message -> get tool use -> execute -> feed back -> repeat.
        """
        request_stats = self._new_request_stats()

        allowed, retry_after = self._enforce_rate_limit(user_id)
        if not allowed:
            self._append_audit_event(
                user_id,
                "rate_limited",
                {"retry_after_seconds": retry_after},
            )
            request_stats["status"] = "rate_limited"
            self._store_last_request_stats(user_id, request_stats)
            return (
                "Rate limit reached. "
                f"Please wait about {retry_after}s before sending another request."
            )

        static_response = self._try_static_response(
            user_message,
            provider=self.provider,
            model=self._resolve_model_for_provider(self.provider),
        )
        if static_response is not None:
            request_stats["status"] = "cached"
            request_stats["input_tokens"] = 0
            request_stats["output_tokens"] = 0
            request_stats["estimated_usd"] = 0.0
            self._store_last_request_stats(user_id, request_stats)
            return static_response

        # Auto-fallback is DISABLED. If Gemini fails, we retry-once or return
        # a friendly error — no silent switch to Anthropic.
        try:
            response = self._process_with_provider(
                self.provider,
                user_id,
                user_message,
                persist_history=True,
                use_existing_history=True,
                request_stats=request_stats,
            )
            request_stats["status"] = "success"
            self._store_last_request_stats(user_id, request_stats)
            return response
        except Exception as primary_exc:
            if self.provider == "google" and self._is_soft_google_response_error(primary_exc):
                self._append_audit_event(
                    user_id,
                    "provider_soft_error",
                    {
                        "provider": self.provider,
                        "error_type": type(primary_exc).__name__,
                        "error_preview": str(primary_exc)[:200],
                    },
                )
                request_stats["status"] = "soft_error"
                self._store_last_request_stats(user_id, request_stats)
                return "Gemini returned an empty response. Please retry your request."

            # Gemini 400 from malformed history — clear and retry with fresh context.
            if self._is_history_corruption_error(primary_exc):
                logger.warning(
                    "History corruption detected for user %d — clearing and retrying: %s",
                    user_id,
                    str(primary_exc)[:200],
                )
                self._append_audit_event(
                    user_id,
                    "conversation_reset",
                    {"reason": "history_corruption_400", "error": str(primary_exc)[:200]},
                )
                with self._state_lock:
                    self.conversations.pop(user_id, None)
                try:
                    response = self._process_with_provider(
                        self.provider,
                        user_id,
                        user_message,
                        persist_history=True,
                        use_existing_history=False,
                        request_stats=request_stats,
                    )
                    request_stats["status"] = "success"
                    self._store_last_request_stats(user_id, request_stats)
                    return response
                except Exception as retry_exc:
                    logger.error("Retry after history clear also failed: %s", retry_exc)
                    request_stats["status"] = "error"
                    self._store_last_request_stats(user_id, request_stats)
                    return "Request failed after clearing history. Please try again."

            if self._is_recoverable_provider_error(primary_exc):
                self._append_audit_event(
                    user_id,
                    "provider_recoverable_error",
                    {
                        "provider": self.provider,
                        "error_type": type(primary_exc).__name__,
                        "error_preview": str(primary_exc)[:200],
                    },
                )
                request_stats["status"] = "recoverable_error"
                self._store_last_request_stats(user_id, request_stats)
                return "Provider temporarily unavailable. Please retry in a few seconds."

            # Non-recoverable error — propagate to handler
            request_stats["status"] = "error"
            self._store_last_request_stats(user_id, request_stats)
            raise
