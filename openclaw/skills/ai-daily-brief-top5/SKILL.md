---
name: ai-daily-brief-top5
description: Compatibility alias for AI Daily Brief top5 mode
triggers:
  - "/ai_daily_brief_top5"
model: google/gemini-2.5-pro
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
  - Use date-scoped Brave queries (see "Brave Query Construction" below).
  - Run date-scope hard gate before drafting.
  - REJECT any story whose event date is outside the scope bounds.
  - Do NOT backfill with older stories to reach 5 — fewer is correct.
- Latency policy for this alias:
  - Execute retrieval + drafting directly; do not narrate internal pipeline steps.
  - Never claim "python tools unavailable" or "manual processing mode".
  - Keep top5 runs under the canonical top5 budget caps.
  - Use Brave POST requests by default (JSON body), unless transport constraints require GET.

## Brave Query Construction (mandatory — date-scoped queries)

The Brave LLM Context API has NO native date filter. You MUST embed date bounds
directly in the query string `q`. Use these templates:

| Scope | Query template |
|-------|---------------|
| `12h` | `"AI artificial intelligence news developments {YYYY-MM-DD}"` — run one query first; optional day-before overlap query if coverage is weak. |
| `week` | `"AI artificial intelligence top stories week of {MON_DATE} to {SUN_DATE} {YYYY} latest developments launches releases"` — run one broad query first; optional watchlist query if needed. |
| `month` | `"AI artificial intelligence major developments {MONTH_NAME} {YYYY} launches releases breakthroughs"` — run one broad query first; optional watchlist query if needed. |

**Rules:**
- Always include explicit calendar dates (YYYY-MM-DD) in every query.
- Never use a bare query like `"AI news"` without date bounds.
- Adaptive fan-out:
  - Run query #1 (broad scope) first.
  - Run query #2 (watchlist-focused) only if coverage is weak after normalization:
    - fewer than 8 credible candidates, or
    - fewer than 4 unique Tier-1/2 sources.
  - Hard cap: 2 Brave queries.
- Respect Brave rate-limit guidance: keep at least 1 second between Brave requests.

## Date-Scope Hard Gate (mandatory checkpoint before drafting)

- Compute scope bounds:
  - `12h`: `scope_start = now - 12h`, `scope_end = now` (COT)
  - `week`: `scope_start = Monday 00:00 COT`, `scope_end = Sunday 23:59 COT`
  - `month`: `scope_start = 1st 00:00 COT`, `scope_end = last day 23:59 COT`
- For EVERY candidate story, extract the event date from source text.
- **Hard reject** any story whose event date is outside bounds.
- If a story has no determinable date, reject it.
- If fewer than 5 stories remain, that is correct. Add: `Coverage limited by requested time scope.`
- This gate is NON-NEGOTIABLE.

## Output Format (MANDATORY — every story must follow this exact structure)

### Title format:
```
AI Daily Brief — Top 5 | Week of 2026-02-16 to 2026-02-22 (COT)
```
Always include scope bounds and `(COT)` timezone label.

### Per-story format (do not omit any field):
```
### {rank}) {Headline with model/product name} (score: {0.00-1.00}) — {YYYY-MM-DD}
- What happened:
  - {fact bullet 1 from sources}
  - {fact bullet 2 from sources}
- Technical Details: {architecture} | {context window} | {key benchmark or "not disclosed"}
- Why it matters: {1-2 sentence strategic significance}
- Sources: [{Outlet1}](https://url1), [{Outlet2}](https://url2)
```

### CORRECT example:
```
### 1) OpenAI CEO Sam Altman Warns Against "AI Washing" (score: 0.72) — 2026-02-22
- What happened:
  - Sam Altman keynote at India AI Impact Summit criticized companies blaming AI for operational failures
  - Called for accountability standards separating genuine AI integration from marketing claims
- Technical Details: not applicable (policy/industry statement, no model release)
- Why it matters: Signals industry maturity pivot — largest lab CEO publicly distancing from hype cycle
- Sources: [OpenTools](https://opentools.ai/news/...), [Reuters](https://reuters.com/technology/...)
```

### INCORRECT — DO NOT produce output like this:
```
1. Sam Altman Calls Out "AI Washing" | Feb 22, 2026

• OpenAI CEO warns against blame-shifting
• Sources: OpenTools, OpenAI official
```
This fails because: wrong date format (not ISO 8601), no score, no structure, no Technical Details, bare source names.

## Pre-Send Validation Checklist (execute ALL checks before sending)

```
CHECK 1 — DATE FORMAT: Every headline ends with " — YYYY-MM-DD"?
  ✓ "— 2026-02-22"    ✗ "| Feb 22, 2026"    ✗ "| Feb 2026"
CHECK 2 — DATE IN SCOPE: Every event date within scope_start..scope_end?
CHECK 3 — SCORE: Every headline has "(score: X.XX)"?
CHECK 4 — STRUCTURE: Every story has What happened + Technical Details + Why it matters + Sources?
CHECK 5 — SOURCES: Every source is [Name](https://url)? No bare outlet names?
CHECK 6 — TITLE: Includes scope bounds + (COT)?
CHECK 7 — TECHNICAL DETAILS: Every story has a Technical Details line?
```
If ANY check fails → fix before sending. Do NOT send failing output.

## Quality Gates
- Vague dates like "Feb 2026" are NOT valid — find the specific day or use `~YYYY-MM-DD (estimated)`.
- A story from Feb 6 MUST NOT appear in a "Week of Feb 16-22" brief. Importance does not override scope.
- Sources must be clickable markdown links `[Name](url)`. Never bare outlet names.
- Each story must include Technical Details (even if "not applicable" or "not disclosed").
- If no credible stories in scope: `No high-confidence AI updates in this window.`
