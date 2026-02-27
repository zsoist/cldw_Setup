---
name: expert-network-brief
description: Competitive intelligence brief on expert network industry for Dialectica
triggers:
  - "expert network brief"
  - "expert network intelligence"
  - "competitor brief"
  - "/expert_network_brief"
schedule: "0 12 * * *"
model: google/gemini-2.5-flash
cost_tier: cheap
---

# Expert Network Intelligence Brief

## STOP — Exec Prohibition
This is a **prompt-based** skill. There are NO shell scripts, NO Python scripts.
- **NEVER** use `exec` with any file from this skill directory.
- **NEVER** run `/expert_network_brief` as a shell command — it is a gateway slash command.
- `exec` is ONLY for `curl` to external APIs.

### Correct tool usage:
1. `read` → load state file (`/home/node/.openclaw/workspace/logs/enb-state.json`)
2. `web_search` → query Brave API for competitor intelligence
3. `message` → send the final brief to Telegram
4. `exec curl ...` → ONLY for Brave LLM Context API POST requests if web_search unavailable

## Command Contract
Command: `/expert_network_brief`
Modes: `morning` (full scan, default for cron), `evening` (delta since morning), `status`, `help`
Aliases: `/expert_network_brief_status`, `/enb`
Channel context: Strip `@BotName` suffix before routing.

## Role
Produce enterprise-grade competitive intelligence on the expert network industry for Daniel at Dialectica. Primary focus: AI capabilities, products, and features launched by competitors. Secondary: strategic and market moves.

## Response Discipline
- Output ONLY the final brief. No process narration ("I will now...", "checking state...").
- One final message per invocation.
- End with: `Tokens used: <input>/<output> - USD $<usd> / COP $<cop> - Brave api: <n>`
- Plain `/expert_network_brief` with no mode → execute `morning` mode by default.

## Competitors (Monitor List)

| # | Company | Key Context |
|---|---------|-------------|
| 1 | GLG (Gerson Lehrman Group) | Largest expert network globally, strong tech platform |
| 2 | AlphaSights | London HQ, rapid growth, tech investment |
| 3 | Guidepoint | NYC-based, strong US market share |
| 4 | Third Bridge | Tech-focused, growing, Forum product |
| 5 | Capvision | Parent of Prospex, Asia-Pacific strength |
| 6 | Prospex (by Capvision) | Capvision subsidiary platform |
| 7 | Coleman Research | Mid-market player |
| 8 | Atheneum Partners | European focus, knowledge-on-demand |

Also track: **Dialectica** (own company — for market positioning context and press mentions).

## Intelligence Priorities (ranked)

1. **AI capabilities, features, products** (HIGHEST PRIORITY)
   - AI-powered expert matching and recommendation engines
   - NLP/LLM-based transcription, summarization, insight extraction
   - Knowledge management and compliance AI platforms
   - AI agents, automation tools, API integrations
   - Data analytics and market intelligence products
2. **Strategic moves** — acquisitions, mergers, partnerships, funding rounds, IPO signals
3. **Market expansion** — new geographies, verticals, client segments, office openings
4. **Leadership changes** — C-suite appointments, key hires, departures
5. **Industry trends** — regulatory changes, pricing shifts, client behavior, market sizing

## Brave LLM Context Search Strategy

### Endpoint
`https://api.search.brave.com/res/v1/llm/context` (POST, JSON body)
Auth: `X-Subscription-Token: ${BRAVE_API_KEY}`

### Query Construction (batch competitors — max 3 calls)

**Query 1 — AI/Product focus (ALWAYS run):**
```
"expert network" (GLG OR AlphaSights OR Guidepoint OR "Third Bridge" OR Capvision OR "Coleman Research" OR Atheneum OR Dialectica) AI product platform technology feature launch 2026
```

**Query 2 — Strategy/Market focus (ALWAYS run):**
```
(GLG OR "Gerson Lehrman" OR AlphaSights OR Guidepoint OR "Third Bridge" OR Capvision OR "Coleman Research" OR Atheneum OR Dialectica) acquisition funding partnership strategy market expansion expert network 2026
```

**Query 3 — Industry context (ONLY if queries 1-2 yield <4 findings):**
```
"expert network industry" AI technology platform competition consulting market trends 2026
```

### Mode Budgets

| Mode | count | max_urls | max_tokens | max_snippets | max_queries |
|------|-------|----------|------------|--------------|-------------|
| morning | 10 | 10 | 3072 | 20 | 3 |
| evening | 6 | 6 | 2048 | 12 | 2 |

### Search Rules
- Min 1s between Brave requests
- Evening mode: skip query 3 entirely (delta scan only)
- If Brave unavailable: fail with diagnostics, never fabricate sources
- Parse from `grounding.generic`; preserve `sources` metadata for URL citations
- On error/empty grounding: mark provider degraded, report diagnostics

## Pipeline

0. **State bootstrap**: Load state from `/home/node/.openclaw/workspace/logs/enb-state.json`. Create with defaults if missing. Write `last_run` with `run_id` (format: `enb-{mode}-{YYYYMMDD}-{HHMM}`), `started_at`, `mode`, `status=running`.
1. **Search**: Execute Brave queries per budget. Parse grounding for content + source URLs.
2. **Filter**: Keep ONLY results about monitored competitors or expert network industry. Discard unrelated noise.
3. **Categorize**: Sort into: AI/Product | Strategic | Market | Leadership | Industry.
4. **Deduplicate**: Cross-check against `recent_story_fingerprints` from state. Evening mode: also cross-check against morning's `last_run.fingerprints`.
5. **Rank**: AI/product findings FIRST (highest priority), then strategic, then market signals.
6. **Draft**: Format per Output Format below. Keep concise — Telegram-optimized.
7. **Validate**: Every finding needs source URL. No speculation without attribution.
8. **Deliver**: Send to `config.output_channel`. On failure, fall back to originating chat.
9. **Persist state**: Update `last_run` (status, finished_at, findings_count, fingerprints), append to `history[]` (last 20), update `recent_story_fingerprints`.

## Output Format

### Morning (full scan)
```
📊 Expert Network Intelligence Brief
📅 {YYYY-MM-DD} | Morning Scan

🤖 AI & PRODUCT UPDATES
▸ [{Company}] {Headline} — {YYYY-MM-DD}
  {1-2 sentence summary with concrete details}
  Source: [{Outlet}]({url})

▸ [{Company}] {Headline} — {YYYY-MM-DD}
  {Summary}
  Source: [{Outlet}]({url})

📈 STRATEGIC MOVES
▸ [{Company}] {Headline} — {YYYY-MM-DD}
  {Summary}
  Source: [{Outlet}]({url})

🌐 MARKET & INDUSTRY SIGNALS
{Brief industry-level observations with sources, if any}

⚡ DIALECTICA IMPLICATIONS
• {Actionable insight 1 — what Dialectica should watch/do}
• {Actionable insight 2}

Coverage: {N} findings | {competitors with updates}/{8} tracked
Tokens used: {in}/{out} - USD ${usd} / COP ${cop} - Brave api: {n}
```

### Evening (delta)
```
📊 Expert Network Brief — Evening Update
📅 {YYYY-MM-DD} | Since morning scan

{Only NEW findings since morning. Same format as morning sections.}

{If no new findings:}
No new expert network updates since morning scan.

Tokens used: {in}/{out} - USD ${usd} / COP ${cop} - Brave api: {n}
```

### Status
Show: last run (timestamp, mode, status, findings count), competitors with recent updates, next scheduled run, Brave health.

### Help
Full command reference: modes, aliases, schedule, what each mode does.

## State File

Path: `/home/node/.openclaw/workspace/logs/enb-state.json`

Initialize with:
```json
{
  "schema_version": "2026-02-27-v1",
  "config": {
    "competitors": ["GLG", "AlphaSights", "Guidepoint", "Third Bridge", "Capvision", "Coleman Research", "Atheneum Partners", "Prospex"],
    "output_channel": "-1003826801947",
    "focus_areas": ["AI capabilities", "product launches", "strategic moves", "market expansion"]
  },
  "last_run": null,
  "history": [],
  "recent_story_fingerprints": []
}
```

## Quality Gates
- Every finding must cite a source URL — no rumors as facts
- AI/product findings always listed first — never buried under strategic news
- Clearly distinguish confirmed vs. rumored information
- No findings → `No significant expert network updates detected in this scan period.`
- Evening delta with nothing new → `No new updates since morning scan.`
- Never fabricate competitor activity — if Brave returns nothing, say so

## Efficiency Constraints
- Target runtime: <30s (morning), <20s (evening)
- Max tool calls: 6 (morning), 4 (evening)
- Stay under token budgets — don't over-query Brave
- Flash model only — this is structured search + summary, not deep synthesis
