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

fd, tmp_path = tempfile.mkstemp(prefix=".ai-brief-state.", suffix=".json", dir=os.path.dirname(runtime_path) or ".")
os.close(fd)
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2)
    f.write("\n")
os.replace(tmp_path, runtime_path)
PY

chmod 600 "$RUNTIME_PATH"
echo "Merged AI brief state -> $RUNTIME_PATH"
