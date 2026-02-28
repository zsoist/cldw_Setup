#!/usr/bin/env bash
# Reconcile stale ai_daily_brief "running" state entries.
set -euo pipefail

STATE_FILE="${1:-/root/.openclaw/workspace/logs/news-brief-state.json}"
STALE_AFTER_SECONDS="${STALE_AFTER_SECONDS:-900}"
DRY_RUN="${DRY_RUN:-0}"
DEFAULT_ERROR_REASON="${DEFAULT_ERROR_REASON:-Recovered stale running state (auto-finalized by reconcile-ai-brief-state.sh)}"

if [ ! -f "$STATE_FILE" ]; then
  echo "State file not found: $STATE_FILE" >&2
  exit 1
fi

python3 - "$STATE_FILE" "$STALE_AFTER_SECONDS" "$DRY_RUN" "$DEFAULT_ERROR_REASON" <<'PY'
import datetime as dt
import json
import os
import sys
import tempfile
from typing import Any

state_path = sys.argv[1]
stale_after_seconds = int(sys.argv[2])
dry_run = str(sys.argv[3]).strip() == "1"
default_error_reason = sys.argv[4]

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

def now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

with open(state_path, "r", encoding="utf-8") as f:
    state = json.load(f)

if not isinstance(state, dict):
    raise RuntimeError("ai-brief state root is not an object")

last_run = state.get("last_run")
if not isinstance(last_run, dict):
    print("NOOP last_run_missing")
    sys.exit(0)

status = str(last_run.get("status") or "").strip().lower()
if status != "running":
    print(f"NOOP status={status or 'null'}")
    sys.exit(0)

started_at = last_run.get("started_at")
started_dt = parse_ts(started_at)
now_dt = dt.datetime.now(dt.timezone.utc)
age_seconds = None
stale = False
stale_reason = ""

if started_dt is None:
    stale = True
    stale_reason = "started_at_missing_or_invalid"
else:
    age_seconds = int((now_dt - started_dt).total_seconds())
    if age_seconds >= stale_after_seconds:
        stale = True
        stale_reason = f"stale_age_seconds={age_seconds}"

if not stale:
    if age_seconds is None:
        print("NOOP running_without_parseable_started_at")
    else:
        print(f"NOOP running_age_seconds={age_seconds}")
    sys.exit(0)

run_id = (last_run.get("run_id") or "unknown")
error_text = (last_run.get("error") or "").strip()
if error_text:
    if "Recovered stale running state" not in error_text:
        error_text = f"{error_text} | {default_error_reason}"
else:
    if started_dt is not None:
        error_text = f"{default_error_reason}; started_at={started_dt.replace(microsecond=0).isoformat().replace('+00:00','Z')}"
    else:
        error_text = f"{default_error_reason}; started_at=unknown"

last_run["status"] = "failed"
last_run["finished_at"] = now_iso_utc()
last_run["error"] = error_text
delivery = last_run.get("delivery")
if not isinstance(delivery, dict):
    delivery = {}
    last_run["delivery"] = delivery
if not delivery.get("result"):
    delivery["result"] = "failed"
if not delivery.get("error"):
    delivery["error"] = "Run interrupted before finalize"

if dry_run:
    print(f"STALE run_id={run_id} reason={stale_reason}")
    sys.exit(0)

fd, tmp_path = tempfile.mkstemp(prefix=".ai-brief-state.reconcile.", suffix=".json", dir=os.path.dirname(state_path) or ".")
os.close(fd)
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
    f.write("\n")
os.replace(tmp_path, state_path)
os.chmod(state_path, 0o600)
# Restore ownership to sentinel:systemd-journal so the gateway container (uid=999) can read it.
import subprocess
subprocess.run(["chown", "sentinel:systemd-journal", state_path], check=False)
print(f"RECOVERED run_id={run_id} reason={stale_reason} stale_after_seconds={stale_after_seconds}")
PY
