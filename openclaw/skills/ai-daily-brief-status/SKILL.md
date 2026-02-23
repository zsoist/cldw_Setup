---
name: ai-daily-brief-status
description: Compatibility alias for AI Daily Brief status mode
triggers:
  - "/ai_daily_brief_status"
model: google/gemini-2.5-flash
cost_tier: standard
---

# AI Daily Brief Status Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_status`.

## Behavior
- Force mode `status` and execute `ai-daily-brief` status flow immediately.
- Status must read and report from `/home/node/.openclaw/workspace/logs/ai-brief-state.json`.
- If no run exists yet, report explicitly and do not fail.
- Preserve canonical provider/delivery diagnostics behavior.
- Do not attribute failures to pairing/sub-agent issues unless current runtime evidence explicitly shows that condition.
