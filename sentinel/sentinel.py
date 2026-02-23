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
from tools import GOOGLE_TOOLS, TOOLS, execute_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("sentinel")

SYSTEM_PROMPT = """You are Sentinel, a sysadmin bot managing a Hetzner CPX22 VPS.

Your responsibilities:
- Monitor system health (CPU, RAM, disk, network)
- Manage Docker containers (especially the OpenClaw gateway)
- Run security audits and report findings
- Create backups of OpenClaw configuration
- Diagnose and fix common issues
- Report status clearly and concisely

Rules:
- Only use the tools provided. Do not suggest manual SSH commands.
- If something looks dangerous or unusual, alert the user and wait for confirmation.
- Keep responses concise — this is Telegram, not an essay.
- If a restart or destructive action is requested, confirm before executing.
- Never expose secrets, tokens, or API keys in responses.
- Use bullet points for status reports.

The VPS runs:
- Ubuntu 24.04 LTS
- Docker with OpenClaw gateway container
- UFW firewall (SSH only inbound)
- fail2ban for SSH protection
- This bot (Sentinel) as a systemd service
"""


class SentinelAgent:
    """Provider-backed sysadmin agent with tool use."""

    def __init__(self, config: SentinelConfig):
        self.config = config
        self.provider = config.provider

        self.client: Any
        self.google_module: Any | None = None
        if self.provider == "anthropic":
            if Anthropic is None:
                raise RuntimeError(
                    "SENTINEL_PROVIDER=anthropic requires the anthropic package. "
                    "Install dependencies from sentinel/requirements.txt"
                )
            self.client = Anthropic(api_key=config.anthropic_api_key)
        elif self.provider == "google":
            self.google_module, self.client = self._init_google_client()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        self.conversations: dict[int, list[dict[str, Any]]] = {}
        self._last_activity: dict[int, float] = {}
        self._request_windows: dict[int, deque[float]] = {}
        self._state_lock = threading.Lock()

        self._audit_log_path = Path(self.config.audit_log_file)
        self._audit_prev_hash = ""
        self._prepare_audit_log()
        self._configure_file_logging()

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

    def _prepare_history(self, user_id: int) -> list[dict[str, Any]]:
        """Get mutable message history and expire stale sessions."""
        now = time.monotonic()
        with self._state_lock:
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

        if len(raw) <= 4000:
            return raw, False

        truncated = {
            "truncated": True,
            "original_length": len(raw),
            "preview": raw[:3500],
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
        """Keep the latest conversation window to control token usage."""
        if len(history) <= 20:
            return history
        return history[-20:]

    def _call_anthropic(self, history: list[dict[str, Any]]) -> Any:
        return self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )

    def _call_google(self, history: list[dict[str, Any]]) -> Any:
        return self.client.generate_content(
            history,
            tools=GOOGLE_TOOLS,
            generation_config={"max_output_tokens": self.config.max_tokens},
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

        if not assistant_parts:
            assistant_parts = [{"text": ""}]

        assistant_turn = {"role": role or "model", "parts": assistant_parts}
        return "".join(text_chunks).strip(), tool_calls, assistant_turn

    def _run_anthropic_loop(self, user_id: int, history: list[dict[str, Any]]) -> str:
        """Run Anthropic tool-use loop until a final text response is produced."""
        for _ in range(self.config.max_tool_iterations):
            response = self._call_anthropic(history)

            if response.stop_reason == "tool_use":
                assistant_content = response.content
                history.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type != "tool_use":
                        continue
                    logger.info("Executing tool: %s(%s)", block.name, json.dumps(block.input)[:200])
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
            self.conversations[user_id] = self._truncate_history(history)
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

    def _run_google_loop(self, user_id: int, history: list[dict[str, Any]]) -> str:
        """Run Gemini function-calling loop until a final text response is produced."""
        for _ in range(self.config.max_tool_iterations):
            response = self._call_google(history)
            text_response, tool_calls, assistant_turn = self._extract_google_response(response)
            history.append(assistant_turn)

            if tool_calls:
                function_responses = []
                for call in tool_calls:
                    tool_name = call["name"]
                    tool_input = call.get("input", {})
                    logger.info("Executing tool: %s(%s)", tool_name, json.dumps(tool_input)[:200])
                    result = execute_tool(tool_name, tool_input)
                    serialized, truncated = self._serialize_tool_result(result)
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
                self.conversations[user_id] = history
                continue

            final_text = text_response or "No response generated."
            history = self._truncate_history(history)
            self.conversations[user_id] = history
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

    def process_message(self, user_id: int, user_message: str) -> str:
        """Process a user message through the configured provider with tool use.

        Implements the agentic loop: send message -> get tool use -> execute -> feed back -> repeat.
        """
        allowed, retry_after = self._enforce_rate_limit(user_id)
        if not allowed:
            self._append_audit_event(
                user_id,
                "rate_limited",
                {"retry_after_seconds": retry_after},
            )
            return (
                "Rate limit reached. "
                f"Please wait about {retry_after}s before sending another request."
            )

        history = self._prepare_history(user_id)
        if self.provider == "google":
            history.append({"role": "user", "parts": [{"text": user_message}]})
        else:
            history.append({"role": "user", "content": user_message})

        self._append_audit_event(
            user_id,
            "user_message",
            {"chars": len(user_message), "preview": user_message[:200]},
        )

        history = self._truncate_history(history)
        self.conversations[user_id] = history

        if self.provider == "google":
            return self._run_google_loop(user_id, history)
        return self._run_anthropic_loop(user_id, history)
