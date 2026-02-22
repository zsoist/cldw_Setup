---
name: ai-daily-brief-top5
description: Compatibility alias for AI Daily Brief top5 mode
triggers:
  - "/ai_daily_brief_top5"
model: haiku
cost_tier: standard
---

# AI Daily Brief Top5 Alias

## Role
Compatibility command shim for users invoking `/ai_daily_brief_top5`.

## Behavior
- Force mode `top5` and execute full `ai-daily-brief` behavior immediately.
- Do not ask clarifying questions for mode/slot selection.
- Persist state for this invocation:
  - set `last_run.started_at` + `status=running` at start
  - set `last_run.finished_at` + final `status` (`success|partial|failed`) at end
  - set `last_run.error` on failures (never leave null if failed)
- Preserve ranking, validation, and delivery routing behavior from canonical skill.
- If provider retrieval degrades, deliver partial brief instead of aborting silently.

## Output
- Same output contract as `ai-daily-brief` in `top5` mode.
