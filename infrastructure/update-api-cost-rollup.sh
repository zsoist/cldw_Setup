#!/usr/bin/env bash
# Build a combined API cost rollup from AI Brief state + Sentinel summary.
set -euo pipefail

AI_BRIEF_STATE="${1:-/root/.openclaw/workspace/logs/ai-brief-state.json}"
SENTINEL_SUMMARY="${2:-/var/log/sentinel/api-cost-summary.json}"
OUTPUT_FILE="${3:-/root/.openclaw/workspace/logs/api-cost-rollup.json}"

mkdir -p "$(dirname "$OUTPUT_FILE")"

python3 - "$AI_BRIEF_STATE" "$SENTINEL_SUMMARY" "$OUTPUT_FILE" <<'PY'
import datetime as dt
import json
import os
import tempfile
from typing import Any
import sys

ai_brief_state_path = sys.argv[1]
sentinel_summary_path = sys.argv[2]
output_path = sys.argv[3]


def safe_load(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def parse_ts(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def to_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def week_key(ts: dt.datetime) -> str:
    iso = ts.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_key(ts: dt.datetime) -> str:
    return f"{ts.year:04d}-{ts.month:02d}"


def ensure_bucket(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    bucket = mapping.get(key)
    if not isinstance(bucket, dict):
        bucket = {
            "usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "runs": 0,
            "success_runs": 0,
            "failed_runs": 0,
            "partial_runs": 0,
            "unknown_runs": 0,
        }
        mapping[key] = bucket
    return bucket


def inc_bucket(bucket: dict[str, Any], usd: float, input_tokens: int, output_tokens: int, status: str) -> None:
    bucket["usd"] = round(float(bucket.get("usd", 0.0)) + usd, 8)
    bucket["input_tokens"] = int(bucket.get("input_tokens", 0)) + input_tokens
    bucket["output_tokens"] = int(bucket.get("output_tokens", 0)) + output_tokens
    bucket["runs"] = int(bucket.get("runs", 0)) + 1
    status_norm = (status or "").strip().lower()
    if status_norm == "success":
        bucket["success_runs"] = int(bucket.get("success_runs", 0)) + 1
    elif status_norm == "failed":
        bucket["failed_runs"] = int(bucket.get("failed_runs", 0)) + 1
    elif status_norm == "partial":
        bucket["partial_runs"] = int(bucket.get("partial_runs", 0)) + 1
    else:
        bucket["unknown_runs"] = int(bucket.get("unknown_runs", 0)) + 1


def aggregate_ai_brief_costs(state: dict[str, Any]) -> dict[str, Any]:
    daily: dict[str, Any] = {}
    weekly: dict[str, Any] = {}
    monthly: dict[str, Any] = {}
    total = {
        "usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "runs": 0,
        "success_runs": 0,
        "failed_runs": 0,
        "partial_runs": 0,
        "unknown_runs": 0,
    }

    seen_run_ids: set[str] = set()
    runs: list[dict[str, Any]] = []
    history = state.get("history")
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict):
                runs.append(item)
    last_run = state.get("last_run")
    if isinstance(last_run, dict):
        run_id = last_run.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            runs.append(last_run)

    for run in runs:
        run_id = str(run.get("run_id") or "").strip()
        if run_id and run_id in seen_run_ids:
            continue
        if run_id:
            seen_run_ids.add(run_id)

        cost = run.get("cost_estimate")
        if not isinstance(cost, dict):
            continue
        usd = to_float(cost.get("estimated_usd"))
        input_tokens = to_int(cost.get("input_tokens"))
        output_tokens = to_int(cost.get("output_tokens"))
        status = str(run.get("status") or "unknown")

        ts = parse_ts(run.get("finished_at")) or parse_ts(run.get("started_at")) or dt.datetime.now(dt.timezone.utc)
        day = ts.date().isoformat()
        week = week_key(ts)
        month = month_key(ts)

        inc_bucket(ensure_bucket(daily, day), usd, input_tokens, output_tokens, status)
        inc_bucket(ensure_bucket(weekly, week), usd, input_tokens, output_tokens, status)
        inc_bucket(ensure_bucket(monthly, month), usd, input_tokens, output_tokens, status)
        inc_bucket(total, usd, input_tokens, output_tokens, status)

    return {
        "all_time": total,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
    }


def normalize_sentinel_summary(summary: dict[str, Any]) -> dict[str, Any]:
    totals = summary.get("totals")
    if not isinstance(totals, dict):
        return {
            "all_time": {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0, "success_calls": 0, "error_calls": 0},
            "daily": {},
            "weekly": {},
            "monthly": {},
        }
    return {
        "all_time": totals.get("all_time") if isinstance(totals.get("all_time"), dict) else {
            "usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0,
            "success_calls": 0,
            "error_calls": 0,
        },
        "daily": totals.get("daily") if isinstance(totals.get("daily"), dict) else {},
        "weekly": totals.get("weekly") if isinstance(totals.get("weekly"), dict) else {},
        "monthly": totals.get("monthly") if isinstance(totals.get("monthly"), dict) else {},
    }


def combine_period(ai_map: dict[str, Any], sentinel_map: dict[str, Any]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    keys = set(ai_map.keys()) | set(sentinel_map.keys())
    for key in sorted(keys):
        ai_bucket = ai_map.get(key) if isinstance(ai_map.get(key), dict) else {}
        s_bucket = sentinel_map.get(key) if isinstance(sentinel_map.get(key), dict) else {}
        combined[key] = {
            "usd": round(to_float(ai_bucket.get("usd")) + to_float(s_bucket.get("usd")), 8),
            "input_tokens": to_int(ai_bucket.get("input_tokens")) + to_int(s_bucket.get("input_tokens")),
            "output_tokens": to_int(ai_bucket.get("output_tokens")) + to_int(s_bucket.get("output_tokens")),
            "ai_brief_runs": to_int(ai_bucket.get("runs")),
            "sentinel_api_calls": to_int(s_bucket.get("calls")),
            "sentinel_success_calls": to_int(s_bucket.get("success_calls")),
            "sentinel_error_calls": to_int(s_bucket.get("error_calls")),
        }
    return combined


ai_state = safe_load(ai_brief_state_path, {})
if not isinstance(ai_state, dict):
    ai_state = {}

sentinel_summary = safe_load(sentinel_summary_path, {})
if not isinstance(sentinel_summary, dict):
    sentinel_summary = {}

ai_agg = aggregate_ai_brief_costs(ai_state)
sentinel_agg = normalize_sentinel_summary(sentinel_summary)

overall_all_time = {
    "usd": round(to_float(ai_agg["all_time"].get("usd")) + to_float(sentinel_agg["all_time"].get("usd")), 8),
    "input_tokens": to_int(ai_agg["all_time"].get("input_tokens")) + to_int(sentinel_agg["all_time"].get("input_tokens")),
    "output_tokens": to_int(ai_agg["all_time"].get("output_tokens")) + to_int(sentinel_agg["all_time"].get("output_tokens")),
    "ai_brief_runs": to_int(ai_agg["all_time"].get("runs")),
    "sentinel_api_calls": to_int(sentinel_agg["all_time"].get("calls")),
    "sentinel_success_calls": to_int(sentinel_agg["all_time"].get("success_calls")),
    "sentinel_error_calls": to_int(sentinel_agg["all_time"].get("error_calls")),
}

report = {
    "version": "2026-02-26-v1",
    "generated_at": now_iso(),
    "currency": "USD",
    "sources": {
        "ai_brief": ai_agg,
        "sentinel": sentinel_agg,
    },
    "totals": {
        "all_time": overall_all_time,
        "daily": combine_period(ai_agg["daily"], sentinel_agg["daily"]),
        "weekly": combine_period(ai_agg["weekly"], sentinel_agg["weekly"]),
        "monthly": combine_period(ai_agg["monthly"], sentinel_agg["monthly"]),
    },
}

fd, tmp_path = tempfile.mkstemp(prefix=".api-cost-rollup.", suffix=".json", dir=os.path.dirname(output_path) or ".")
os.close(fd)
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
    f.write("\n")
os.replace(tmp_path, output_path)
os.chmod(output_path, 0o600)

print(f"Wrote API cost rollup -> {output_path}")
print(
    "All-time USD: "
    + f"{report['totals']['all_time']['usd']:.6f} "
    + f"(ai_brief_runs={report['totals']['all_time']['ai_brief_runs']}, "
    + f"sentinel_api_calls={report['totals']['all_time']['sentinel_api_calls']})"
)
PY
