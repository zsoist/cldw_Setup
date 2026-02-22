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
- Interpret this command exactly as: `/ai_daily_brief watchlist`
- Route immediately to `ai-daily-brief`
- Preserve all existing ranking, validation, delivery routing, and state persistence behavior
- Do not implement separate logic in this alias
