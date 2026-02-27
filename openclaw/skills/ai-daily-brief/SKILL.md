---
name: ai-daily-brief
description: Produce a source-grounded, stateful AI news briefing for Telegram
triggers:
  - "ai daily brief"
  - "ai news brief"
  - "top ai news"
  - "top ai stories"
  - "/ai_daily_brief"
schedule: "10 12 * * *"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief Skill

## STOP — Exec Prohibition (READ THIS FIRST)
This is a **prompt-based** skill. There are NO shell scripts, NO Python scripts, NO executables.
- **NEVER** use `exec` with any file from this skill directory.
- **NEVER** try to run `/ai_daily_brief` as a shell command — it is a gateway slash command, not a binary.
- The `exec` tool is ONLY allowed for `curl` commands to external APIs.

### Correct tool usage:
1. `read` → load state file (`/home/node/.openclaw/workspace/logs/ai-brief-state.json`)
2. `web_search` → query Brave API for AI news
3. `message` → send the final brief to Telegram
4. `exec curl ...` → ONLY for Brave LLM Context API POST requests if web_search is unavailable

## Command Contract
Stable command: `/ai_daily_brief`

Modes: `morning`, `evening`, `top5 [12h|week|month|YYYY-MM]`, `builder`, `watchlist [add|remove <topic>]`, `status`, `feedback <run_id> <1-5> [comment]`, `history [n]`, `diff`, `help`

Aliases: `/ai_daily_brief_morning`, `_evening`, `_top5`, `_builder`, `_watchlist`, `_status`

Channel context: Strip `@BotName` suffix before routing (remove `@[A-Za-z0-9_]+`). Commands from approved groups processed identically to DM commands.

## Role
Produce a high-signal, low-noise AI news briefing for Daniel. Scheduled run: daily 07:10 COT (previous-day top stories); all other modes on-demand.

## Response Discipline
- Output ONLY the final brief. Never output process narration ("I will now...", "checking...", "state file shows...", "Reasoning:").
- Send exactly one final result message per invocation.
- Always end with: `Tokens used: <input>/<output> - USD $<usd> / COP $<cop>` (append ` - Brave api: <n>` when Brave was used; use `n/a` if metrics unavailable).
- Plain `/ai_daily_brief` with no mode → ask: `Choose mode: morning, evening, top5, builder, watchlist, status, feedback, history, diff, or help.`
- Natural-language intent: "top ai news of the month" → `top5 month`, "this week" → `top5 week`, "last 12h" → `top5 12h`

## Inputs
- Timezone: `America/Bogota` (COT)
- State: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Brave API key: `BRAVE_API_KEY` env var
- Provider config in state: `config.provider`, `config.brave_llm_context`
- Delivery target: `config.output_channel` → `output_channel` (legacy) → originating chat (fallback)
- Coverage windows:
  - Scheduled daily (07:10 COT): previous calendar day (00:00–23:59 COT)
  - Morning: last 12-16h | Evening: last 10-14h
  - Top5 default: current week Mon 00:00 – Sun 23:59 COT
  - Top5 `12h`: rolling 12h | `month`: calendar month | `YYYY-MM`: exact month
- Source tiers: T1=labs/vendors/regulators, T2=Reuters/Bloomberg/FT/WSJ/The Information, T3=secondary summaries, T4=social (corroborated only)

## Brave LLM Context API
- Endpoint: `https://api.search.brave.com/res/v1/llm/context` (POST preferred, JSON body)
- Auth: `X-Subscription-Token: ${BRAVE_API_KEY}`
- Required fields: `q`, `count`, `search_lang`, `country`, `context_threshold_mode` (`strict|balanced|lenient|disabled`), context budget fields (`maximum_number_of_urls`, `maximum_number_of_tokens`, `maximum_number_of_snippets`, `maximum_number_of_tokens_per_url`, `maximum_number_of_snippets_per_url`)
- Threshold: top5/watchlist=`strict`, full/builder=`balanced`
- Keep `enable_local=null` for AI news; `true` only for location-based requests.
- If `config.brave_llm_context.goggles` configured, include on every request.
- Parse from `grounding.generic`; preserve `sources` metadata for URL citations.
- On error/empty grounding: mark provider degraded, fail run with diagnostics (never fabricate sources).

### Mode Budgets

| Mode | count | max_urls | max_tokens | max_snippets | per_url_tokens | per_url_snippets |
|------|-------|----------|------------|--------------|----------------|------------------|
| full | 14 | 14 | 6144 | 30 | 2048 | 20 |
| top5 | 8 | 10 | 3072 | 20 | 2048 | 20 |
| builder | 12 | 12 | 5120 | 24 | 2048 | 20 |
| watchlist | 8 | 8 | 2048 | 16 | 2048 | 20 |

### Query Construction (date-scoped, mandatory)
Brave has NO native date filter — embed date bounds in `q`:
- `12h`: `"AI artificial intelligence news developments {YYYY-MM-DD}" site:reuters.com OR site:bloomberg.com OR site:theverge.com OR site:techcrunch.com`
- `week`: `"AI artificial intelligence top stories week of {MON_DATE} to {SUN_DATE} {YYYY}" latest developments launches releases`
- `month`: `"AI artificial intelligence major developments {MONTH_NAME} {YYYY}" launches releases breakthroughs`

**Rules**: Always include explicit calendar dates. Adaptive fan-out: query #1 (broad, date-scoped) first → query #2 (watchlist-focused) only if <8 candidates or <4 T1/T2 sources. Hard cap for top5: 2 Brave queries. Min 1s between requests. Watchlist query: append terms from state (e.g., `openai anthropic "google deepmind" "meta ai" "ai regulation"`).

### Execution Rules
- Execute retrieval + synthesis in one pass. No streaming progress.
- Never claim "python tools unavailable". Use Brave grounding + model reasoning directly.
- Skip second query if first has sufficient coverage. Prioritize shipping quickly over exhaustive recall.

## Pipeline
0. **State bootstrap (mandatory first action)**: Load state → write `last_run` with `run_id`, `started_at`, `mode`, `status=running`. On any failure: set `status=failed` + `error` before returning.
1. **Collect**: Brave LLM Context with mode budget caps. Optional second query per fan-out rules. If Brave unavailable, stop with provider error.
2. **Normalize**: canonical URL, publisher, UTC+COT timestamps.
3. **Deduplicate**: canonical URL + title fuzzy + cross-run suppression from state.
4. **Cluster**: group by event/topic (not outlet-by-outlet).
5. **Rank** (weighted): impact=0.28, credibility=0.22, novelty=0.18, relevance=0.14, freshness=0.10, confidence=0.08
6. **Anti-hype penalty**: single low-tier source, uncontextualized benchmarks, uncorroborated viral claims.
6b. **Date-scope hard gate (top5 — mandatory, NON-NEGOTIABLE)**:
   - Compute scope bounds as ISO 8601 dates in COT.
   - **Hard reject** stories with event date outside bounds or no determinable date.
   - If <5 remain, that is correct — NEVER backfill with out-of-scope stories. Add: `Coverage limited by requested time scope.`
7. **Draft**: Story synthesis with source attribution. Each headline MUST include `YYYY-MM-DD` event date + model/product name (or "name not publicly disclosed").
   - **Technical Details (mandatory)**: architecture, params, context window, benchmarks, compute tier. If unavailable: `Technical details: not yet publicly disclosed.`
8. **Validate**: required sections, no duplicates, credible sources, parseable `YYYY-MM-DD` dates, clickable `[Outlet](url)` links.
9. **Render**: Telegram-safe markdown.
10. **Deliver**: `status` → reply in originating chat only. Other modes → output channel (with short ACK in originating chat). If already in output channel, reply there. On delivery failure: fall back to originating chat + mark failure reason.
11. **Persist**: run metadata + story fingerprints + suppression state.
12. **Persist stories**: Append to `workspace/outputs/summaries/ai-brief-stories-YYYY-MM.json` (enables trend analysis).
13. **Finalize state (mandatory last action)**: `finished_at`, `status` (success|partial|failed), delivery metadata, `error` (null on success), `cost_estimate` {input_tokens, output_tokens, model, estimated_usd}, append to `history[]` (last 20), update `providers.brave_llm_context.last_probe_at`.

## Path Safety
- Slash commands are commands, not file paths. Never read `/aibrief_status` or `workspace/aibrief_status`.
- State file: always use absolute path `/home/node/.openclaw/workspace/logs/ai-brief-state.json`.

## Delivery Routing
- Resolve target: `config.output_channel` → `output_channel` (legacy) → originating chat.
- Normalize plain usernames to `@username`.
- Brief body → target; originating chat → concise ACK (timestamp, slot, target, status).
- Persist delivery metadata in `last_run.delivery`: `target`, `result`, `message_parts`, `error`.

## Output Formats

### Full mode (morning, evening)
1. Title + COT timestamp
2. Executive Snapshot (2-4 bullets)
3. Ranked Stories: Headline (model/product + score + YYYY-MM-DD), What happened, Why it matters, Technical Details, Signal vs Hype, Watch next, Sources
4. Quick Hits
5. Builder/Agent Corner
6. Strategic Take
7. Tomorrow Watchlist
8. Confidence & Gaps

### top5
Title with scope: `AI Daily Brief — Top 5 | Week of YYYY-MM-DD to YYYY-MM-DD (COT)`

Each story (mandatory structure):
```
### {rank}) {Headline with model/product} (score: {0.00-1.00}) — {YYYY-MM-DD}
- What happened:
  - {fact bullet 1 from sources}
  - {fact bullet 2 from sources}
- Technical Details: {architecture} | {context window} | {key benchmark or "not disclosed"}
- Why it matters: {1-2 sentence strategic significance}
- Sources: [{Outlet1}](https://url1), [{Outlet2}](https://url2)
```

### builder
Builder/agent tooling changes, APIs, evals, infra implications, experiments.

### watchlist
Current topics + deltas + priority signals + unknowns.
- `add <topic>`: append (lowercase, deduplicated). `remove <topic>`: exact match (case-insensitive), error if not found.

### feedback, history, diff, help (all use Flash)
- `feedback <run_id> <1-5> [comment]`: Record rating in `feedback[]` state. Confirm with run ID + rating.
- `history [n]`: Last N runs (default 5, max 20): run_id, slot, mode, status, started_at, counts, cost.
- `diff`: Compare last two completed runs — new/dropped stories + score movements.
- `help`: Full command reference in Telegram markdown (modes, scopes, aliases, @BotName format).

### status (use Flash)
Show: last run + last success, candidate/cluster counts, cost estimate, provider health + diagnostics (endpoint, key, threshold, budget, last probe), delivery state, output channel, watchlist, recent feedback (last 3), schedule.
- Do not claim pairing/sub-agent blocking without explicit current-run evidence (runtime `running=false`, empty `allowFrom`, or error text containing the failure).

## Quality Gates
- No rumors as facts. Mark conflicts explicitly. No stories → `No high-confidence AI updates in this window.`
- **Date gate (zero tolerance)**: Every headline needs `YYYY-MM-DD` (ISO 8601). Vague "Feb 2026" without a day is INVALID — find the actual day or reject. Out-of-scope stories REJECTED regardless of importance.
- **Source link gate**: Every source must be `[Outlet](url)`, never bare outlet names.
- **Technical depth gate**: Every story needs Technical Details (even if "not yet publicly disclosed").
- Retrieval degraded → partial brief + list gaps. Missing `BRAVE_API_KEY` → report + setup command.
- Channel unreachable → failure notice to originating chat (never silently drop output).

## Pre-Send Checklist (mandatory before delivering top5)
1. Every headline ends with `— YYYY-MM-DD` (ISO 8601, NOT "Feb 22, 2026" or "Feb 2026")
2. Every event date is within scope bounds (out-of-scope → remove entirely)
3. Every headline has `(score: X.XX)`
4. Every story has: What happened (2+ bullets), Technical Details, Why it matters, Sources (clickable `[Name](url)`)
5. Title includes scope bounds: `AI Daily Brief — Top 5 | Week of YYYY-MM-DD to YYYY-MM-DD (COT)`
6. No process narration; telemetry footer present as last line
→ Fix ANY failure before sending. Do NOT send failing output.

## Efficiency Constraints
- Target runtime <60s (top5 <45s). Max tool calls: 8 (top5: 6).
- Concise mode when signal is weak. Skip unchanged stories from last 48h unless updated.
- Stay under configured token budgets; do not request max context for simple updates.
