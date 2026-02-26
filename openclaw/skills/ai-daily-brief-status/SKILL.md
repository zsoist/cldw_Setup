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
- Return one final status payload only (no process narration before status output).
- Status must read and report from `/home/node/.openclaw/workspace/logs/ai-brief-state.json`.
- If no run exists yet, report explicitly and do not fail.
- If `last_run.status=running`, compute age from `started_at`:
  - age >= 900s or invalid/missing `started_at`: report as stale lock and include reconcile hint.
  - age < 900s: report as active run in progress.
- Preserve canonical provider/delivery diagnostics behavior.
- Do not attribute failures to pairing/sub-agent issues unless current runtime evidence explicitly shows that condition.
