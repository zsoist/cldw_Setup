---
name: ai-daily-brief-evening
description: Compatibility alias for AI Daily Brief evening mode
triggers:
  - "/ai_daily_brief_evening"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Evening Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_evening`.

## Behavior
- Interpret this command exactly as: `/ai_daily_brief evening`
- Route immediately to `ai-daily-brief`
- Preserve all existing ranking, validation, delivery routing, and state persistence behavior
- Do not implement separate logic in this alias
