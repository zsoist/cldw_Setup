---
name: ai-daily-brief
description: Produce a source-grounded, stateful AI news briefing for Telegram
triggers:
  - "ai daily brief"
  - "ai news brief"
  - "/ai_daily_brief"
schedule: "10 7,19 * * *"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Skill

## Command Contract (canonical)
Use a single stable command to avoid routing ambiguity:
- `/ai_daily_brief`

Optional mode argument (same command):
- `/ai_daily_brief morning`
- `/ai_daily_brief evening`
- `/ai_daily_brief top5`
- `/ai_daily_brief builder`
- `/ai_daily_brief watchlist [topics]`
- `/ai_daily_brief status`

Compatibility aliases (accepted):
- `/ai_daily_brief_morning`
- `/ai_daily_brief_evening`
- `/ai_daily_brief_top5`
- `/ai_daily_brief_builder`
- `/ai_daily_brief_watchlist`
- `/ai_daily_brief_status`

## Role
Produce a high-signal, low-noise AI news briefing for Daniel twice daily, optimized for Telegram readability and operational decision value.

## Inputs
- Local timezone: `America/Bogota`
- State file: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Brave API key: `BRAVE_API_KEY` from runtime env
- Provider config in state:
  - `config.provider` (expect `brave_llm_context`)
  - `config.brave_llm_context` (endpoint + token budget + threshold)
- Delivery target from state:
  - `config.output_channel` (preferred)
  - fallback: `output_channel` (legacy key)
  - accepted formats: `@channel_username`, `channel_username`, or numeric chat id
- Coverage window:
  - Morning: previous evening run or last 12-16h
  - Evening: previous morning run or last 10-14h
- Trusted source tiers:
  - Tier 1: official labs/vendors/model cards/regulators
  - Tier 2: Reuters/Bloomberg/FT/WSJ/The Information
  - Tier 3: secondary summaries (context only)
  - Tier 4: social posts only if corroborated

## Brave LLM Context Provider Contract
- Primary retrieval endpoint: `https://api.search.brave.com/res/v1/llm/context`
- Auth header: `X-Subscription-Token: ${BRAVE_API_KEY}`
- Prefer POST with JSON body for predictable parameter control.
- Required request fields:
  - `q` (query)
  - `count` (default from state or 20)
  - `search_lang`, `country`
  - `context_threshold_mode` (`strict|balanced|lenient|disabled`)
  - context budget fields:
    - `maximum_number_of_urls`
    - `maximum_number_of_tokens`
    - `maximum_number_of_snippets`
    - `maximum_number_of_tokens_per_url`
    - `maximum_number_of_snippets_per_url`
- Parse from `grounding.generic`, and include `grounding.map` / `grounding.poi` only when relevant.
- Keep `sources` metadata so every top story can cite URLs and hostnames.
- If provider errors or returns empty grounding:
  - mark provider degraded in run status
  - continue with fallback web search only as partial brief
  - never fabricate source-backed claims

### Brave Query/Token Budget Defaults
- `full` mode: `count=20`, `maximum_number_of_tokens=8192`
- `top5` mode: `count=12`, `maximum_number_of_tokens=4096`
- `builder` mode: bias to tooling queries, `count=15`, `maximum_number_of_tokens=6144`
- `watchlist` mode: narrow watchlist terms, `count=10`, `maximum_number_of_tokens=3072`

## Pipeline (deterministic first, then synthesis)
0. **State bootstrap (mandatory, first action)**:
   - load `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
   - write `last_run` with `run_id`, `started_at`, inferred `slot`/`mode`, and `status=running`
   - if any subsequent step fails, update `last_run.status=failed` and `last_run.error=<reason>` before returning
1. **Collect**:
   - call Brave LLM Context first for AI queries in coverage window
   - if Brave is unavailable, use fallback web search and mark partial mode
2. **Normalize**: canonical URL, normalized publisher, UTC+COT timestamps.
3. **Deduplicate**:
   - canonical URL dedupe
   - title/fuzzy near-duplicate suppression
   - cross-run duplicate suppression from state
4. **Cluster**: group by event/topic (not outlet-by-outlet summaries).
5. **Rank** with weighted score:
   - impact 0.28
   - credibility 0.22
   - novelty 0.18
   - relevance 0.14
   - freshness 0.10
   - confidence 0.08
6. **Anti-hype penalty**:
   - single low-tier source only
   - benchmark claims without method context
   - uncorroborated viral/social claims
7. **Draft**: story-level synthesis with explicit source attribution.
8. **Validate**:
   - required sections present by mode
   - no duplicate stories in same run
   - each top story has credible source(s)
9. **Render**: Telegram-safe sections, concise bullets.
10. **Deliver**:
   - `status` mode: reply in originating chat only.
   - non-`status` modes: deliver final brief to configured output channel when present; then send a short ACK in originating chat.
   - if channel delivery fails, fall back to originating chat and mark failure reason.
11. **Persist**: run metadata + story fingerprints + suppression state.
12. **Finalize state (mandatory, last action)**:
   - write `finished_at`
   - write final `status` (`success|partial|failed`)
   - write delivery metadata + `error` field (null on success, explicit string on failure)

## Path Safety Rules (critical)
- Treat slash commands as commands, never as file paths.
- Never read paths like `/aibrief_status` or `workspace/aibrief_status`.
- For AI brief state, always use absolute path: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`.

## Delivery Routing Rules
- Resolve `delivery_target` from state in this order:
  1. `config.output_channel`
  2. `output_channel` (legacy)
  3. originating chat (fallback)
- Normalize plain usernames to `@username`.
- Do not duplicate the full brief in both places:
  - brief body goes to `delivery_target`
  - originating chat gets concise ACK (timestamp, slot/mode, target, status)
- Persist delivery metadata under `last_run.delivery`:
  - `target`
  - `result` (`ok`, `fallback_origin_chat`, `failed`)
  - `message_parts`
  - `error` (if any)

## Output Structure
### Full mode (default, `morning`, `evening`)
1. Title line with slot + COT timestamp
2. Executive Snapshot (2-4 bullets)
3. Ranked Top Stories:
   - What happened
   - Why it matters
   - Signal vs Hype
   - Watch next
   - Sources
4. Quick Hits
5. Builder / Agent Corner
6. Strategic Take
7. Tomorrow Watchlist
8. Confidence & Gaps

### `top5`
- Title + Top 5 + concise sources + watch-next mini-list

### `builder`
- Builder/agent tooling changes, APIs, evals, infra implications, experiments

### `watchlist`
- Watchlist deltas + priority signals + unresolved unknowns

### `status`
Return:
- last run + last success (morning/evening)
- candidate/cluster counts from last completed run
- provider health (ok/degraded/unknown)
- provider diagnostics:
  - `provider` name
  - endpoint in use
  - key present (`yes/no`)
  - threshold mode
  - token budget for current mode
- Telegram delivery state (last send path/result)
- active output channel target
- state file path + loaded status
- expected schedule (`07:10` and `19:00` COT)

## Quality Gates
- Do not present rumors as facts.
- Mark conflicting reports explicitly.
- If no credible stories: `No high-confidence AI updates in this window.`
- If retrieval degraded: send partial brief and list missing coverage.
- If `BRAVE_API_KEY` is missing: report provider as unconfigured and return setup command.
- If target channel is configured but unreachable (forbidden/not admin):
  - send concise failure notice to originating chat
  - do not silently drop brief output

## Efficiency Constraints
- Target runtime <90s
- Max tool calls: 10
- Default to concise mode when signal is weak
- Avoid repeating unchanged stories from last 48h unless materially updated
- Keep retrieval under configured token budgets; do not request max context for simple factual updates
