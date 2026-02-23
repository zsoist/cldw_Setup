---
name: ai-daily-brief-evening
description: Compatibility alias for AI Daily Brief evening mode
triggers:
  - "/ai_daily_brief_evening"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief Evening Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_evening`.

## Behavior
- Force slot `evening` in full mode and execute `ai-daily-brief` behavior immediately.
- Return only the final evening brief output (no internal process narration).
- Persist start/end/error metadata in `last_run`.
- Preserve canonical ranking, validation, delivery routing, and state behavior.
