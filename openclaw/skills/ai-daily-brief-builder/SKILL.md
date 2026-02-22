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
- Interpret this command exactly as: `/ai_daily_brief builder`
- Route immediately to `ai-daily-brief`
- Preserve all existing ranking, validation, delivery routing, and state persistence behavior
- Do not implement separate logic in this alias
