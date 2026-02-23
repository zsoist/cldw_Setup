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
- Accept explicit scope suffixes (`12h`, `week`, `month`, `month YYYY-MM`) and pass through unchanged.
- Default time scope is current COT week (Monday-Sunday) unless user explicitly requests month scope.
- If user asks "top stories of the month" (or similar), force monthly scope.
- Persist state for this invocation:
  - set `last_run.started_at` + `status=running` at start
  - set `last_run.finished_at` + final `status` (`success|partial|failed`) at end
  - set `last_run.error` on failures (never leave null if failed)
- Preserve ranking, validation, and delivery routing behavior from canonical skill.
- If provider retrieval degrades, deliver partial brief instead of aborting silently.
- **CRITICAL: Apply all date-scope gates from canonical ai-daily-brief SKILL.md:**
  - Use date-scoped Brave queries (see "Brave Query Construction" in canonical skill).
  - Run pipeline step 6b (date-scope hard gate) before drafting.
  - REJECT any story whose event date is outside the scope bounds.
  - Do NOT backfill with older stories to reach 5 — fewer is correct.

## Output
- Same output contract as `ai-daily-brief` in `top5` mode.
- Each story headline MUST include `YYYY-MM-DD` event date (ISO 8601). Use `~YYYY-MM-DD (estimated)` when date is inferred from context. Reject stories without parseable dates.
- **Vague dates like "Feb 2026" are NOT valid.** Find the specific day from sources or use estimated format.
- Each story must include explicit model/product name when known, or explicitly mark `model name not publicly disclosed`.
- Each story must include a Technical Details one-liner (architecture type + context window + key benchmark if available). Mark `not disclosed` if no public data.
- Sources must be clickable markdown links (`[Outlet](https://...)`). Never use bare outlet names.
