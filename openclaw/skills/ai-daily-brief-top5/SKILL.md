---
name: ai-daily-brief-top5
description: AI Daily Brief top5 mode alias
triggers:
  - "/ai_daily_brief_top5"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief — Top5 Alias

Prompt-based skill. Tools: `read`, `message`, `exec curl` (Brave LLM Context API only). Never use `web_search` — always use `exec curl` for Brave LLM Context API. Never exec scripts.

## Behavior
- Force mode `top5`. Accept scope suffix: `12h|week|month|YYYY-MM`. Default: current COT week (Mon-Sun).
- Natural language mapping: "of the month" → month, "last 12h" → 12h.
- Return only final top5 output. No process narration.

## State management
- State file: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Before writing new run: if prior `last_run.status=running` and age >= 900s → set to `failed`. If age < 900s → return "already running".
- Write `last_run` with run_id, started_at, status=running at start. Write finished_at + final status at end.

## Brave query (date-scoped, mandatory)
`POST https://api.search.brave.com/res/v1/llm/context` — Auth: `X-Subscription-Token: ${BRAVE_API_KEY}`
Budget: count=5, max_tokens=1024, max_urls=6, per_url_tokens=512, snippets=12, per_url_snippets=6. Threshold: strict.
Embed date bounds in `q` (Brave has no date filter):
- `12h`: `"AI news developments {YYYY-MM-DD}" site:reuters.com OR site:techcrunch.com`
- `week`: `"AI top stories week of {MON} to {SUN} {YYYY} launches releases"`
- `month`: `"AI major developments {MONTH} {YYYY} launches breakthroughs"`
Max 2 queries. Min 1s between. Query #2 only if <8 candidates or <4 T1/T2 sources.

## Date-scope hard gate (NON-NEGOTIABLE)
Compute COT bounds → hard reject stories outside scope or with no date. <5 remaining is correct — never backfill. Add: `Coverage limited by requested time scope.`

## Output format (mandatory)
Title: `AI Daily Brief — Top 5 | Week of YYYY-MM-DD to YYYY-MM-DD (COT)`

Per story:
```
### {rank}) {Headline with model/product} (score: {0.00-1.00}) — {YYYY-MM-DD}
- What happened:
  - {fact bullet from sources}
- Technical Details: {architecture | benchmarks | "not disclosed"}
- Why it matters: {1-2 sentences}
- Sources: [{Outlet}](url)
```

## Pre-send checks
1. Every headline ends `— YYYY-MM-DD` (not "Feb 22, 2026")
2. Every date within scope bounds
3. Every headline has `(score: X.XX)`
4. Every story has: What happened + Technical Details + Why it matters + Sources `[Name](url)`
5. Title includes scope bounds + (COT)
6. Brave api count as last line (gateway adds usage footer automatically)
Fix ANY failure before sending.

## Delivery
DM-triggered runs → deliver in originating chat (message tool is DM-constrained, cannot send to channels). Cron runs → send to `config.output_channel` + ACK in originating chat. On failure: fall back to originating chat.

## Ranking
Impact=0.28, credibility=0.22, novelty=0.18, relevance=0.14, freshness=0.10, confidence=0.08. Anti-hype: penalize single-source, uncontextualized benchmarks, viral claims.
