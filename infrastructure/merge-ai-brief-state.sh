#!/usr/bin/env bash
# Merge AI brief state template into runtime state while preserving runtime values.
set -euo pipefail

TEMPLATE_PATH="${1:-/root/openclaw-project/openclaw/workspace/logs/ai-brief-state.json}"
RUNTIME_PATH="${2:-/root/.openclaw/workspace/logs/ai-brief-state.json}"

if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "Template state not found: $TEMPLATE_PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$RUNTIME_PATH")"

python3 - "$TEMPLATE_PATH" "$RUNTIME_PATH" <<'PY'
import json
import os
import sys
import tempfile
from typing import Any

template_path = sys.argv[1]
runtime_path = sys.argv[2]

LEGACY_BRAVE_DEFAULTS = {
    "count": 20,
    "maximum_number_of_urls": 20,
    "maximum_number_of_tokens": 8192,
    "maximum_number_of_snippets": 50,
    "maximum_number_of_tokens_per_url": 4096,
    "maximum_number_of_snippets_per_url": 50,
    "context_threshold_mode": "balanced",
}

OPTIMIZED_BRAVE_DEFAULTS = {
    "count": 14,
    "maximum_number_of_urls": 14,
    "maximum_number_of_tokens": 6144,
    "maximum_number_of_snippets": 30,
    "maximum_number_of_tokens_per_url": 2048,
    "maximum_number_of_snippets_per_url": 20,
    "context_threshold_mode": "balanced",
}

LEGACY_PERFORMANCE_DEFAULTS = {
    "timeout_seconds": 30,
    "max_retries": 2,
    "backoff_seconds": [1, 2, 4],
}

OPTIMIZED_PERFORMANCE_DEFAULTS = {
    "timeout_seconds": 22,
    "max_retries": 1,
    "backoff_seconds": [1, 2],
}

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def merge_preserve_existing(template: Any, existing: Any) -> Any:
    if isinstance(template, dict) and isinstance(existing, dict):
        out = dict(template)
        for key, value in existing.items():
            if key in out:
                out[key] = merge_preserve_existing(out[key], value)
            else:
                out[key] = value
        return out
    # Preserve runtime value when present, including explicit nulls.
    return existing


def normalize_ai_brief_config(state: Any) -> Any:
    """Migrate legacy high-latency defaults to optimized defaults."""
    if not isinstance(state, dict):
        return state

    if state.get("version") in {"2026-02-22-v2", "2026-02-23-v3"}:
        state["version"] = "2026-02-23-v4"

    config = state.get("config")
    if not isinstance(config, dict):
        return state

    brave_cfg = config.get("brave_llm_context")
    if not isinstance(brave_cfg, dict):
        brave_cfg = {}
        config["brave_llm_context"] = brave_cfg

    for key, optimized_value in OPTIMIZED_BRAVE_DEFAULTS.items():
        current = brave_cfg.get(key)
        legacy = LEGACY_BRAVE_DEFAULTS.get(key)
        if current in (None, "") or current == legacy:
            brave_cfg[key] = optimized_value

    perf_cfg = config.get("performance")
    if not isinstance(perf_cfg, dict):
        perf_cfg = {}
        config["performance"] = perf_cfg

    for key, optimized_value in OPTIMIZED_PERFORMANCE_DEFAULTS.items():
        current = perf_cfg.get(key)
        legacy = LEGACY_PERFORMANCE_DEFAULTS.get(key)
        if current in (None, "") or current == legacy:
            perf_cfg[key] = optimized_value

    return state

template = load_json(template_path)
if os.path.exists(runtime_path):
    try:
        existing = load_json(runtime_path)
        merged = merge_preserve_existing(template, existing)
    except Exception:
        # Corrupt runtime state: recover with template
        merged = template
else:
    merged = template

merged = normalize_ai_brief_config(merged)

fd, tmp_path = tempfile.mkstemp(prefix=".ai-brief-state.", suffix=".json", dir=os.path.dirname(runtime_path) or ".")
os.close(fd)
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2)
    f.write("\n")
os.replace(tmp_path, runtime_path)
PY

chmod 600 "$RUNTIME_PATH"
echo "Merged AI brief state -> $RUNTIME_PATH"
