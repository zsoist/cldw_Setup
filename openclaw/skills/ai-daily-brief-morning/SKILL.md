---
name: ai-daily-brief-morning
description: Compatibility alias for AI Daily Brief morning mode
triggers:
  - "/ai_daily_brief_morning"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Morning Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_morning`.

## Behavior
- Interpret this command exactly as: `/ai_daily_brief morning`
- Route immediately to `ai-daily-brief`
- Preserve all existing ranking, validation, delivery routing, and state persistence behavior
- Do not implement separate logic in this alias
