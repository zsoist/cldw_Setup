---
name: ai-daily-brief-status
description: Self-contained status check for AI Daily Brief
triggers:
  - "/ai_daily_brief_status"
model: google/gemini-2.5-flash
cost_tier: cheap
---

# AI Daily Brief Status

## STOP — Tool Restrictions
- **NEVER** use `exec` for this skill. No scripts exist. No `.sh`, `.py`, or binary to run.
- **NEVER** load or read the main `ai-daily-brief/SKILL.md` — this status skill is self-contained.
- **ONLY** use the `read` tool to read the JSON state file below, then format and send the result.

## Steps (exactly 2 tool calls)
1. `read` → `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
2. `message` → send formatted status to the user

## Status Report Format
Parse the JSON state file and output:

```
AI Daily Brief Status
─────────────────────
Last run: {last_run.mode} — {last_run.status} ({last_run.finished_at or "n/a"})
Error: {last_run.error or "none"}
Duration: {last_run.duration_ms}ms
Output channel: {config.output_channel or "not set"}
Provider: {config.provider or "not set"}
Watchlist: {watchlist.topics joined by ", " or "empty"}
History: {len(history)} runs recorded
Consecutive errors: {consecutiveErrors or 0}
```

## Edge Cases
- If state file is empty or missing: report `No AI brief runs recorded yet.`
- If `last_run.status=running` and age >= 900s: report `⚠️ Stale lock detected (started {age}s ago). May need manual reset.`
- If `last_run.status=running` and age < 900s: report `⏳ Run in progress (started {age}s ago).`
- Do not attribute failures to pairing/sub-agent issues unless the error field explicitly says so.
