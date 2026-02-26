---
name: ai-daily-brief-builder
description: Compatibility alias for AI Daily Brief builder mode
triggers:
  - "/ai_daily_brief_builder"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief Builder Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_builder`.

## Behavior
- Force mode `builder` and execute full `ai-daily-brief` behavior immediately.
- Return only the final builder output (no internal process narration).
- Apply canonical stale-lock recovery before new run state:
  - stale `last_run.status=running` (>=900s or invalid `started_at`) -> finalize prior run as failed.
  - active `running` (<900s) -> return concise "already running" notice and do not overwrite state.
- Persist start/end/error metadata in `last_run`.
- Preserve canonical ranking, validation, delivery routing, and state behavior.
