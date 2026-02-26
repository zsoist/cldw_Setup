"""Crash-safe API usage cost tracking for Sentinel.

Design goals:
- append-only event log (JSONL) for durability
- atomic summary snapshots for quick reads
- low-overhead incremental aggregation (daily/weekly/monthly)
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(ts: datetime | None = None) -> str:
    value = ts or _utc_now()
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _day_key(ts: datetime) -> str:
    return ts.date().isoformat()


def _week_key(ts: datetime) -> str:
    iso = ts.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _month_key(ts: datetime) -> str:
    return f"{ts.year:04d}-{ts.month:02d}"


def _empty_bucket() -> dict[str, Any]:
    return {
        "usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "calls": 0,
        "success_calls": 0,
        "error_calls": 0,
    }


def _empty_section() -> dict[str, Any]:
    return {
        "all_time": _empty_bucket(),
        "daily": {},
        "weekly": {},
        "monthly": {},
    }


@dataclass(frozen=True)
class _Pricing:
    input_per_million: float
    output_per_million: float


# Approximate list prices in USD per 1M tokens. Override in code if needed.
_MODEL_PRICING: dict[str, _Pricing] = {
    "google/gemini-2.5-flash": _Pricing(input_per_million=0.10, output_per_million=0.40),
    "google/gemini-2.5-pro": _Pricing(input_per_million=1.25, output_per_million=5.00),
    "anthropic/claude-haiku-4-5": _Pricing(input_per_million=0.80, output_per_million=4.00),
    "anthropic/claude-sonnet-4-6": _Pricing(input_per_million=3.00, output_per_million=15.00),
    "anthropic/claude-opus-4-6": _Pricing(input_per_million=15.00, output_per_million=75.00),
}

_PROVIDER_DEFAULT_PRICING: dict[str, _Pricing] = {
    "google": _Pricing(input_per_million=0.10, output_per_million=0.40),
    "anthropic": _Pricing(input_per_million=0.80, output_per_million=4.00),
}


def _normalize_provider(provider: str) -> str:
    return (provider or "").strip().lower() or "unknown"


def _normalize_model(provider: str, model: str) -> str:
    normalized = (model or "").strip().lower()
    if not normalized:
        return f"{provider}/unknown"
    if "/" in normalized:
        left, right = normalized.split("/", 1)
        if left in {"google", "anthropic"}:
            normalized = f"{left}/{right}"
    elif provider in {"google", "anthropic"}:
        normalized = f"{provider}/{normalized}"

    # Alias normalization.
    alias_map = {
        "google/flash": "google/gemini-2.5-flash",
        "google/gemini-flash": "google/gemini-2.5-flash",
        "google/gemini-pro": "google/gemini-2.5-pro",
        "google/pro": "google/gemini-2.5-pro",
        "anthropic/claude-haiku": "anthropic/claude-haiku-4-5",
        "anthropic/claude-sonnet": "anthropic/claude-sonnet-4-6",
        "anthropic/claude-opus": "anthropic/claude-opus-4-6",
    }
    return alias_map.get(normalized, normalized)


def _resolve_pricing(provider: str, model: str) -> _Pricing:
    provider_norm = _normalize_provider(provider)
    model_norm = _normalize_model(provider_norm, model)
    if model_norm in _MODEL_PRICING:
        return _MODEL_PRICING[model_norm]

    # Heuristic fallbacks for close variants.
    if "gemini-2.5-flash" in model_norm:
        return _MODEL_PRICING["google/gemini-2.5-flash"]
    if "gemini-2.5-pro" in model_norm:
        return _MODEL_PRICING["google/gemini-2.5-pro"]
    if "haiku" in model_norm:
        return _MODEL_PRICING["anthropic/claude-haiku-4-5"]
    if "sonnet" in model_norm:
        return _MODEL_PRICING["anthropic/claude-sonnet-4-6"]
    if "opus" in model_norm:
        return _MODEL_PRICING["anthropic/claude-opus-4-6"]

    return _PROVIDER_DEFAULT_PRICING.get(provider_norm, _Pricing(0.0, 0.0))


class APICostTracker:
    """Track provider usage events and maintain aggregated spend summaries."""

    def __init__(
        self,
        usage_log_file: str,
        summary_file: str,
        retention_days: int = 180,
    ) -> None:
        self._usage_log_path = Path(usage_log_file)
        self._summary_path = Path(summary_file)
        self._retention_days = max(30, retention_days)
        self._lock = threading.Lock()
        self._prepare_paths()

    def _prepare_paths(self) -> None:
        for path in (self._usage_log_path, self._summary_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        if not self._usage_log_path.exists():
            self._usage_log_path.touch(mode=0o640)
        if not self._summary_path.exists():
            self._write_summary(self._new_summary())

    def record(
        self,
        *,
        provider: str,
        model: str,
        status: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        user_id: int | None = None,
        error_type: str | None = None,
        error_preview: str | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Record one API usage event and update aggregated summary."""
        ts = (timestamp or _utc_now()).astimezone(timezone.utc)
        provider_norm = _normalize_provider(provider)
        model_norm = _normalize_model(provider_norm, model)
        input_count = _safe_int(input_tokens)
        output_count = _safe_int(output_tokens)
        status_norm = (status or "unknown").strip().lower() or "unknown"

        pricing = _resolve_pricing(provider_norm, model_norm)
        estimated_usd = (
            (input_count * pricing.input_per_million) + (output_count * pricing.output_per_million)
        ) / 1_000_000.0

        event = {
            "ts": _utc_iso(ts),
            "provider": provider_norm,
            "model": model_norm,
            "status": status_norm,
            "input_tokens": input_count,
            "output_tokens": output_count,
            "estimated_usd": round(estimated_usd, 8),
            "pricing": {
                "input_per_million": pricing.input_per_million,
                "output_per_million": pricing.output_per_million,
            },
            "user_id": user_id,
            "error_type": error_type,
            "error_preview": error_preview[:200] if isinstance(error_preview, str) else None,
        }

        with self._lock:
            self._append_event(event)
            summary = self._load_summary()
            self._apply_event(summary, event, ts)
            self._prune_summary(summary, ts)
            summary["updated_at"] = _utc_iso(ts)
            self._write_summary(summary)

        return event

    def _append_event(self, event: dict[str, Any]) -> None:
        with self._usage_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _load_summary(self) -> dict[str, Any]:
        if not self._summary_path.exists():
            return self._new_summary()
        try:
            data = json.loads(self._summary_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._new_summary()
        except (json.JSONDecodeError, OSError):
            return self._new_summary()

        data.setdefault("version", "2026-02-26-v1")
        data.setdefault("currency", "USD")
        data.setdefault("generated_by", "sentinel")
        data.setdefault("updated_at", _utc_iso())
        data.setdefault("totals", _empty_section())
        data.setdefault("providers", {})
        data.setdefault("models", {})
        return data

    @staticmethod
    def _new_summary() -> dict[str, Any]:
        return {
            "version": "2026-02-26-v1",
            "currency": "USD",
            "generated_by": "sentinel",
            "updated_at": _utc_iso(),
            "totals": _empty_section(),
            "providers": {},
            "models": {},
        }

    def _apply_event(self, summary: dict[str, Any], event: dict[str, Any], ts: datetime) -> None:
        period_keys = {
            "daily": _day_key(ts),
            "weekly": _week_key(ts),
            "monthly": _month_key(ts),
        }
        for section_name, model_key in (
            ("totals", None),
            ("providers", event["provider"]),
            ("models", event["model"]),
        ):
            section = self._resolve_section(summary, section_name, model_key)
            self._increment_section(section, period_keys, event)

    @staticmethod
    def _resolve_section(summary: dict[str, Any], section_name: str, key: str | None) -> dict[str, Any]:
        if section_name == "totals":
            section = summary.get("totals")
            if not isinstance(section, dict):
                section = _empty_section()
                summary["totals"] = section
            return section

        container = summary.get(section_name)
        if not isinstance(container, dict):
            container = {}
            summary[section_name] = container
        section = container.get(key or "")
        if not isinstance(section, dict):
            section = _empty_section()
            container[key or ""] = section
        return section

    @staticmethod
    def _increment_bucket(bucket: dict[str, Any], event: dict[str, Any]) -> None:
        bucket["usd"] = round(_safe_float(bucket.get("usd")) + _safe_float(event.get("estimated_usd")), 8)
        bucket["input_tokens"] = _safe_int(bucket.get("input_tokens")) + _safe_int(event.get("input_tokens"))
        bucket["output_tokens"] = _safe_int(bucket.get("output_tokens")) + _safe_int(event.get("output_tokens"))
        bucket["calls"] = _safe_int(bucket.get("calls")) + 1
        if event.get("status") == "success":
            bucket["success_calls"] = _safe_int(bucket.get("success_calls")) + 1
            bucket["error_calls"] = _safe_int(bucket.get("error_calls"))
        else:
            bucket["success_calls"] = _safe_int(bucket.get("success_calls"))
            bucket["error_calls"] = _safe_int(bucket.get("error_calls")) + 1

    def _increment_section(
        self,
        section: dict[str, Any],
        period_keys: dict[str, str],
        event: dict[str, Any],
    ) -> None:
        all_time = section.get("all_time")
        if not isinstance(all_time, dict):
            all_time = _empty_bucket()
            section["all_time"] = all_time
        self._increment_bucket(all_time, event)

        for period_name, period_key in period_keys.items():
            period_map = section.get(period_name)
            if not isinstance(period_map, dict):
                period_map = {}
                section[period_name] = period_map
            bucket = period_map.get(period_key)
            if not isinstance(bucket, dict):
                bucket = _empty_bucket()
                period_map[period_key] = bucket
            self._increment_bucket(bucket, event)

    def _prune_summary(self, summary: dict[str, Any], ts: datetime) -> None:
        cutoff_day = ts.date() - timedelta(days=self._retention_days)
        for section in [summary.get("totals")] + list((summary.get("providers") or {}).values()) + list(
            (summary.get("models") or {}).values()
        ):
            if not isinstance(section, dict):
                continue
            self._prune_period_map(section.get("daily"), cutoff_day, "daily")
            self._prune_period_map(section.get("weekly"), cutoff_day, "weekly")
            self._prune_period_map(section.get("monthly"), cutoff_day, "monthly")

    @staticmethod
    def _parse_week_start(key: str) -> datetime | None:
        match = re.fullmatch(r"(\d{4})-W(\d{2})", key)
        if not match:
            return None
        year = int(match.group(1))
        week = int(match.group(2))
        try:
            return datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _parse_month_start(key: str) -> datetime | None:
        match = re.fullmatch(r"(\d{4})-(\d{2})", key)
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        if month < 1 or month > 12:
            return None
        return datetime(year=year, month=month, day=1, tzinfo=timezone.utc)

    def _prune_period_map(self, period_map: Any, cutoff_day: Any, period: str) -> None:
        if not isinstance(period_map, dict):
            return
        remove_keys: list[str] = []
        for key in period_map.keys():
            if period == "daily":
                try:
                    key_day = datetime.strptime(key, "%Y-%m-%d").date()
                except ValueError:
                    remove_keys.append(key)
                    continue
                if key_day < cutoff_day:
                    remove_keys.append(key)
                continue

            if period == "weekly":
                start = self._parse_week_start(key)
            else:
                start = self._parse_month_start(key)
            if start is None:
                remove_keys.append(key)
                continue
            if start.date() < cutoff_day:
                remove_keys.append(key)

        for key in remove_keys:
            period_map.pop(key, None)

    def _write_summary(self, summary: dict[str, Any]) -> None:
        summary_dir = self._summary_path.parent
        fd, tmp_path = tempfile.mkstemp(prefix=".api-cost-summary.", suffix=".json", dir=str(summary_dir))
        os.close(fd)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, self._summary_path)
            os.chmod(self._summary_path, 0o640)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
