---
name: ai-daily-brief-builder
description: Compatibility alias for AI Daily Brief builder mode
triggers:
  - "/ai_daily_brief_builder"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Builder Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_builder`.

## Behavior
- Force mode `builder` and execute full `ai-daily-brief` behavior immediately.
- Persist start/end/error metadata in `last_run`.
- Preserve canonical ranking, validation, delivery routing, and state behavior.
