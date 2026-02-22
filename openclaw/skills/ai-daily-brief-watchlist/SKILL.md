---
name: ai-daily-brief-watchlist
description: Compatibility alias for AI Daily Brief watchlist mode
triggers:
  - "/ai_daily_brief_watchlist"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Watchlist Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_watchlist`.

## Behavior
- Force mode `watchlist` and execute full `ai-daily-brief` behavior immediately.
- Persist start/end/error metadata in `last_run`.
- Preserve canonical ranking, validation, delivery routing, and state behavior.
