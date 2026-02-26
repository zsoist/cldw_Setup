---
name: ai-daily-brief-evening
description: Compatibility alias for AI Daily Brief evening mode
triggers:
  - "/ai_daily_brief_evening"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief Evening Alias

## STOP — No Shell Scripts Exist
- **NEVER** use `exec` to run `.sh`, `.py`, or any binary. None exist in this skill directory.
- **NEVER** run `/ai_daily_brief` as a shell command. It is a gateway slash command, not an executable.
- To perform this skill: use `read` (state file), `web_search` (Brave API), `message` (Telegram delivery).

## Behavior
- Force slot `evening` in full mode and follow the `ai-daily-brief` pipeline immediately.
- Return only the final evening brief output (no internal process narration).
- Apply canonical stale-lock recovery before new run state:
  - stale `last_run.status=running` (>=900s or invalid `started_at`) -> finalize prior run as failed.
  - active `running` (<900s) -> return concise "already running" notice and do not overwrite state.
- Persist start/end/error metadata in `last_run`.
- Preserve canonical ranking, validation, delivery routing, and state behavior.
