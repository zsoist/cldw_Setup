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

## Tool restrictions
Tools: `read`, `message`, `exec curl` (Brave LLM Context API only). Never use `web_search`. Never exec scripts or treat `/ai_daily_brief` as a binary.

## Modes
`morning`, `evening`, `top5 [12h|week|month|YYYY-MM]`, `builder`, `watchlist [add|remove <topic>]`, `status`, `feedback`, `history`, `diff`, `help`

## Response Discipline
- Output ONLY the final brief. No `<think>` tags, no process narration, no "I will now..." or "Reasoning:".
- One final message per invocation. Append `Brave api: <n>` at end.
- Plain `/ai_daily_brief` → ask mode. Natural language: "top ai news this week" → top5 week.

## Inputs
- Timezone: `America/Bogota` (COT). State: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Brave API key: `BRAVE_API_KEY` env var
- Delivery: DM sessions → originating chat only. Cron → `config.output_channel`.
- Source tiers: T1=labs/vendors/regulators, T2=Reuters/Bloomberg/FT/WSJ, T3=secondary, T4=social (corroborated only)

## Brave LLM Context API
`POST https://api.search.brave.com/res/v1/llm/context` — Auth: `X-Subscription-Token: ${BRAVE_API_KEY}`

### Mode Budgets

| Mode | count | max_urls | max_tokens | snippets | per_url_tokens |
|------|-------|----------|------------|----------|----------------|
| full | 6 | 8 | 2048 | 15 | 512 |
| top5 | 5 | 6 | 1024 | 12 | 512 |
| builder | 6 | 8 | 2048 | 15 | 512 |
| watchlist | 5 | 6 | 1024 | 12 | 512 |

### Query Construction
Brave has NO date filter — embed dates in `q`:
- `12h`: `"AI news {YYYY-MM-DD}" site:reuters.com OR site:techcrunch.com`
- `week`: `"AI top stories week of {MON} to {SUN} {YYYY} launches releases"`
- `month`: `"AI developments {MONTH} {YYYY} launches breakthroughs"`

Rules: Include explicit dates. Query #2 only if <8 candidates or <4 T1/T2. Top5 hard cap: 2 queries. Min 1s between. Watchlist: append terms from state.

## Pipeline
0. Load state → write `last_run` (run_id, started_at, mode, status=running)
1. Brave LLM Context with budget caps. Skip 2nd query if sufficient.
2. Normalize URLs, publishers, timestamps.
3. Deduplicate (canonical URL + title fuzzy + state fingerprints).
4. Cluster by event, rank: impact=0.28, credibility=0.22, novelty=0.18, relevance=0.14, freshness=0.10, confidence=0.08
5. Anti-hype: penalize single-source, uncontextualized benchmarks, viral claims.
6. **Date gate (top5, NON-NEGOTIABLE)**: reject stories outside scope. <5 is correct — never backfill.
7. Draft with source attribution. Headline MUST include `YYYY-MM-DD`.
8. Validate: required sections, dates, clickable `[Outlet](url)`.
9. Deliver (DM → originating chat, Cron → output_channel).
10. Persist: run metadata, fingerprints, `history[]` (last 20).

## Output: top5
Title: `AI Daily Brief — Top 5 | Week of YYYY-MM-DD to YYYY-MM-DD (COT)`

Per story:
```
### {rank}) {Headline} (score: {0.00-1.00}) — {YYYY-MM-DD}
- What happened:
  - {fact bullet from sources}
- Technical Details: {architecture | benchmarks | "not disclosed"}
- Why it matters: {1-2 sentences}
- Sources: [{Outlet}](url)
```

## Output: full (morning/evening)
Title + COT timestamp → Executive Snapshot (2-4 bullets) → Ranked Stories → Quick Hits → Strategic Take → Confidence & Gaps

## Output: other modes
- `watchlist add/remove <topic>`: modify state, confirm. `status`: read state, format. `feedback <run_id> <1-5>`: record. `history [n]`: last N. `diff`: compare last 2. `help`: command reference.

## Quality Gates
- No rumors as facts. Every headline: `YYYY-MM-DD` (ISO 8601). Every source: `[Outlet](url)`. Every story: Technical Details.
- No stories → `No high-confidence AI updates in this window.`
- Fix ALL failures before sending.
