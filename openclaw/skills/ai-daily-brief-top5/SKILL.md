---
name: ai-daily-brief-top5
description: Compatibility alias for AI Daily Brief top5 mode
triggers:
  - "/ai_daily_brief_top5"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Top5 Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_top5`.

## Behavior
- Interpret this command exactly as: `/ai_daily_brief top5`
- Route immediately to `ai-daily-brief`
- Preserve all existing ranking, validation, delivery routing, and state persistence behavior
- Do not implement separate logic in this alias

## Output
- Same output contract as `ai-daily-brief` in `top5` mode.
