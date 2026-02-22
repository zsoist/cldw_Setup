---
name: ai-daily-brief-status
description: Compatibility alias for AI Daily Brief status mode
triggers:
  - "/ai_daily_brief_status"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Status Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_status`.

## Behavior
- Interpret this command exactly as: `/ai_daily_brief status`
- Route immediately to `ai-daily-brief`
- Preserve all existing ranking, validation, delivery routing, and state persistence behavior
- Do not implement separate logic in this alias
