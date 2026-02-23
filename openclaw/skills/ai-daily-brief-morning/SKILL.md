---
name: ai-daily-brief-morning
description: Compatibility alias for AI Daily Brief morning mode
triggers:
  - "/ai_daily_brief_morning"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief Morning Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_morning`.

## Behavior
- Force slot `morning` in full mode and execute `ai-daily-brief` behavior immediately.
- Return only the final morning brief output (no internal process narration).
- Persist start/end/error metadata in `last_run`.
- Preserve canonical ranking, validation, delivery routing, and state behavior.
