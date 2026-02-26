---
name: ai-daily-brief
description: Produce a source-grounded, stateful AI news briefing for Telegram
triggers:
  - "ai daily brief"
  - "ai news brief"
  - "top ai news"
  - "top ai stories"
  - "/ai_daily_brief"
schedule: "0 7 * * *"
model: google/gemini-2.5-pro
cost_tier: standard
---

# AI Daily Brief Skill

## Execution Model (READ THIS FIRST)
This is a **prompt-based** skill. There are NO shell scripts to execute.
- Do NOT run `exec ai-daily-brief.sh` or any `.sh` file — none exist.
- Do NOT run `exec /ai_daily_brief` — this is a gateway command, not a binary.
- Instead: follow the pipeline steps below using gateway tools: `read` (state file), `web_search` (Brave API), `message` (Telegram delivery).

## Command Contract (canonical)
Use a single stable command to avoid routing ambiguity:
- `/ai_daily_brief`

Optional mode argument (same command):
- `/ai_daily_brief morning`
- `/ai_daily_brief evening`
- `/ai_daily_brief top5`
- `/ai_daily_brief top5 12h`
- `/ai_daily_brief top5 week`
- `/ai_daily_brief top5 month`
- `/ai_daily_brief top5 month YYYY-MM`
- `/ai_daily_brief builder`
- `/ai_daily_brief watchlist`
- `/ai_daily_brief watchlist add <topic>`
- `/ai_daily_brief watchlist remove <topic>`
- `/ai_daily_brief status`
- `/ai_daily_brief feedback <run_id> <1-5> [comment]`
- `/ai_daily_brief history [n]`
- `/ai_daily_brief diff`
- `/ai_daily_brief help`

Compatibility aliases (accepted):
- `/ai_daily_brief_morning`
- `/ai_daily_brief_evening`
- `/ai_daily_brief_top5`
- `/ai_daily_brief_builder`
- `/ai_daily_brief_watchlist`
- `/ai_daily_brief_status`

### Channel Context (Telegram Group/Supergroup)
When invoked from a Telegram group with `@BotName` suffix, strip the suffix before routing:
- `/ai_daily_brief@MangenkyoBot status` → `/ai_daily_brief status`
- `/ai_daily_brief_top5@MangenkyoBot` → `/ai_daily_brief top5` (normalize alias after stripping)
- Pattern: remove `@[A-Za-z0-9_]+` from the command token before any other normalization. Never treat the suffix as an argument.
- Commands from approved interactive chats (`OPENCLAW_TELEGRAM_INTERACTIVE_CHATS`) are processed identically to DM commands — no capability or routing restriction applies.

## Role
Produce a high-signal, low-noise AI news briefing for Daniel. The only scheduled run is daily at 07:00 COT for previous-day top stories; all other modes are on-demand.

## Response Discipline (mandatory)
- Output only the final brief/result (or one concise clarifying question if genuinely blocked).
- Never output process narration such as:
  - "I will now..."
  - "I need to verify..."
  - "state file shows..."
  - "I am now calculating..."
- Never include `Reasoning:` sections, chain-of-thought, or internal checklist text in user-visible output.
- Never send transitional messages like "starting now", "checking configuration", or "next I will...". Send exactly one final result message per invocation.
- Do not stream pipeline progress unless the user explicitly requests `/ai_daily_brief status`.
- Always end the final user-visible message with:
  - `Tokens used: <input>/<output> - USD $<usd> / COP $<cop>`
  - append ` - Brave api: <n>` only when Brave was used in this run.
  - if runtime metrics are unavailable, emit `n/a` values (do not narrate why).
- If user sends plain `/ai_daily_brief` with no mode, ask exactly one concise question:
  - `Choose mode: morning, evening, top5, builder, watchlist, status, feedback, history, diff, or help.`
- For natural-language requests, infer mode/scope and execute immediately without asking when intent is clear:
  - "top ai news of the month" -> `top5 month`
  - "top ai news this week" -> `top5 week`
  - "top ai news last 12h" -> `top5 12h`

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
  - Scheduled daily run (`07:00` COT): previous calendar day (`00:00` to `23:59` COT)
  - Morning: previous evening run or last 12-16h
  - Evening: previous morning run or last 10-14h
  - Top5 `12h`: rolling previous 12 hours from execution time in COT
  - Top5 default: **current calendar week in COT** (Monday 00:00 through Sunday 23:59 containing execution date)
  - Top5 monthly: calendar month in COT (from day 1 00:00 to month-end 23:59)
- Trusted source tiers:
  - Tier 1: official labs/vendors/model cards/regulators
  - Tier 2: Reuters/Bloomberg/FT/WSJ/The Information
  - Tier 3: secondary summaries (context only)
  - Tier 4: social posts only if corroborated

## Brave LLM Context Provider Contract
- Primary retrieval endpoint: `https://api.search.brave.com/res/v1/llm/context`
- Auth header: `X-Subscription-Token: ${BRAVE_API_KEY}`
- Supported methods: GET and POST. Prefer **POST** with JSON body for predictable parameter control.
- Required request fields:
  - `q` (query)
  - `count` (from mode profile; never exceed profile cap)
  - `search_lang`, `country`
  - `context_threshold_mode` (`strict|balanced|lenient|disabled`)
  - context budget fields:
    - `maximum_number_of_urls`
    - `maximum_number_of_tokens`
    - `maximum_number_of_snippets`
    - `maximum_number_of_tokens_per_url`
    - `maximum_number_of_snippets_per_url`
- Parameter validity guardrails (enforce before request):
  - `q`: 1-400 chars, <= 50 words
  - `count`: 1-50
  - `maximum_number_of_urls`: 1-50
  - `maximum_number_of_tokens`: 1024-32768
  - `maximum_number_of_snippets`: 1-100
  - `maximum_number_of_tokens_per_url`: 512-8192
  - `maximum_number_of_snippets_per_url`: 1-100
- Optional fields:
  - `enable_local` (`true|false|null`) for local recall override
  - `goggles` (URL or inline definition) for custom source re-ranking
- Parse from `grounding.generic`, and include `grounding.map` / `grounding.poi` only when relevant.
- `snippets` can contain plain text or JSON-serialized structured blocks (tables/code/schema); preserve both.
- Keep `sources` metadata so every top story can cite URLs and hostnames.
- If provider errors or returns empty grounding:
  - mark provider degraded in run status
  - mark run as failed with explicit provider diagnostics (no generic web-search fallback)
  - never fabricate source-backed claims

### Brave Mode Policy
- **Default request style:** single-search first, then optional second query only if coverage is weak.
- Threshold policy by mode:
  - `top5`: `strict` (precision > recall)
  - `full`: `balanced`
  - `builder`: `balanced`
  - `watchlist`: `strict`
- Local recall policy:
  - For AI news/briefing (default), keep `enable_local=null` and do not send location headers.
  - Use `enable_local=true` only for explicit location-based requests.
- Goggles policy:
  - If `config.brave_llm_context.goggles` is configured, include it on every Brave request.
  - Use goggles to prioritize trusted sources and suppress low-value domains.

### Brave Query/Token Budget Defaults
- `full` mode: `count=14`, `maximum_number_of_urls=14`, `maximum_number_of_tokens=6144`, `maximum_number_of_snippets=30`
- `top5` mode: `count=8`, `maximum_number_of_urls=10`, `maximum_number_of_tokens=3072`, `maximum_number_of_snippets=20`
- `builder` mode: bias to tooling queries, `count=12`, `maximum_number_of_urls=12`, `maximum_number_of_tokens=5120`, `maximum_number_of_snippets=24`
- `watchlist` mode: narrow watchlist terms, `count=8`, `maximum_number_of_urls=8`, `maximum_number_of_tokens=2048`, `maximum_number_of_snippets=16`
- Keep per-url caps conservative for latency:
  - `maximum_number_of_tokens_per_url <= 2048`
  - `maximum_number_of_snippets_per_url <= 20`

### Brave Query Construction (mandatory — date-scoped queries)

The Brave LLM Context API has NO native date filter. You MUST embed date bounds
directly in the query string `q` so the search engine biases results toward the
correct window. Use these templates exactly:

| Scope | Query template (fill placeholders) |
|-------|------------------------------------|
| `12h` | `"AI artificial intelligence news developments {YYYY-MM-DD}" site:reuters.com OR site:bloomberg.com OR site:theverge.com OR site:techcrunch.com` — run one query first; run second (day-before overlap) only if coverage remains weak. |
| `week` | `"AI artificial intelligence top stories week of {MON_DATE} to {SUN_DATE} {YYYY}" latest developments launches releases` — run one broad query first; optional watchlist query if needed. |
| `month` | `"AI artificial intelligence major developments {MONTH_NAME} {YYYY}" launches releases breakthroughs` — run one broad query first; optional watchlist query if needed. |

**Critical rules:**
- Always include the **explicit calendar dates** (YYYY-MM-DD) in every query.
- Never use a bare query like `"AI news"` or `"AI news February 2026"` without specific day/week bounds.
- For `week` scope: compute the Monday and Sunday dates of the target week in COT before constructing the query.
- For `12h` scope: compute the exact start hour in COT and include the calendar date.
- Use adaptive fan-out:
  - Run query #1 (broad, date-scoped) first.
  - Run query #2 (watchlist-focused) only if coverage after normalization is weak:
    - fewer than 8 credible candidates, or
    - fewer than 4 unique Tier-1/2 sources, or
    - obvious watchlist coverage gap.
  - Hard cap for `top5`: 2 Brave queries.
- Respect Brave rate-limit guidance: keep at least 1 second between Brave requests.
- Watchlist-focused query: append watchlist terms from state (e.g., `openai anthropic "google deepmind" "meta ai" "ai regulation"`).

### Latency-First Execution Rules (mandatory)
- Execute retrieval + synthesis in one pass and return final output directly.
- Do not stream internal pipeline progress unless user explicitly calls `/ai_daily_brief status`.
- Never claim "python tools unavailable" or "manual curation mode". Use Brave grounding + model reasoning directly.
- If Brave returns sufficient coverage on first query, skip the second query.
- Prioritize shipping a complete scoped brief quickly over exhaustive long-tail recall.

Example for week of 2026-02-16 to 2026-02-22:
```
Query 1: "AI artificial intelligence top stories week of 2026-02-16 to 2026-02-22 latest developments launches releases"
Query 2: "openai anthropic google deepmind meta ai AI news 2026-02-16 2026-02-17 2026-02-18 2026-02-19 2026-02-20 2026-02-21 2026-02-22"
```

### Top5 Time-Scope Contract (mandatory)
- For `/ai_daily_brief top5 12h`, scope is strict rolling previous 12 hours.
- Default scope for `/ai_daily_brief top5` is the **current week** in `America/Bogota`:
  - Monday 00:00:00 COT to Sunday 23:59:59 COT.
- If user asks monthly intent (examples: "top stories of the month", "this month", `/ai_daily_brief top5 month`), use calendar month scope.
- If user provides explicit month token (`YYYY-MM`), use that exact month.
- Never mix out-of-scope stories into scoped `top5` output.
- If fewer than 5 credible stories exist in the requested scope, report fewer and add: `Coverage limited by requested time scope.`

### Natural-Language Scope Mapping
- "top stories in the last 12 hours" -> `/ai_daily_brief top5 12h`
- "top stories this week" -> `/ai_daily_brief top5 week`
- "top stories this month" / "top stories of the month" -> `/ai_daily_brief top5 month`
- "top stories of February 2026" -> `/ai_daily_brief top5 month 2026-02`

## Pipeline (deterministic first, then synthesis)
0. **State bootstrap (mandatory, first action)**:
   - load `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
   - write `last_run` with `run_id`, `started_at`, inferred `slot`/`mode`, and `status=running`
   - if any subsequent step fails, update `last_run.status=failed` and `last_run.error=<reason>` before returning
1. **Collect**:
   - call Brave LLM Context first for AI queries in coverage window
   - use mode budget caps from this skill (not legacy high-context defaults)
   - run optional second Brave query only under adaptive fan-out rules
   - if Brave is unavailable, stop and return provider error with remediation steps
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
6b. **Date-scope hard gate (top5 only — mandatory checkpoint before drafting)**:
   - Compute the scope bounds as concrete ISO 8601 dates:
     - `12h`: `scope_start = now - 12h`, `scope_end = now` (in COT)
     - `week`: `scope_start = Monday 00:00 COT`, `scope_end = Sunday 23:59 COT`
     - `month`: `scope_start = YYYY-MM-01 00:00 COT`, `scope_end = last day 23:59 COT`
   - For EVERY candidate story, extract or infer the event date from source text.
   - **Hard reject** any story whose event date is before `scope_start` or after `scope_end`.
   - If a story has no determinable date from sources, reject it.
   - If an event spans multiple dates (e.g., "announced Feb 18, shipped Feb 20"), use the most recent date.
   - After filtering: if fewer than 5 stories remain, that is correct — do NOT backfill with out-of-scope stories.
   - Log: `"Date gate: {N} candidates passed, {M} rejected as out-of-scope"` in internal reasoning.
   - This gate is NON-NEGOTIABLE. A story from Feb 6 MUST NOT appear in a "Week of Feb 16-22" brief.
7. **Draft**: story-level synthesis with explicit source attribution.
   - **Event date (mandatory):** Each story headline MUST include its precise event date as `YYYY-MM-DD` (ISO 8601). If exact date is unknown from sources, use `~YYYY-MM-DD (estimated)`. Stories without a parseable date are rejected at the validation gate.
   - **Model/product identifier:** Include the concrete model/product name in the headline or first bullet when available. If source confirms release but does not disclose model/product name, explicitly say `model name not publicly disclosed`.
   - **Technical details (mandatory for top stories when available):** Include a `Technical Details` subsection with:
     - Architecture type (e.g., dense transformer, sparse MoE, diffusion, SSM/Mamba, hybrid)
     - Parameter count or scale tier (if publicly disclosed; mark as `not disclosed` otherwise)
     - Context window (tokens)
     - Key capability deltas vs prior version or closest competitor
     - Benchmark results with methodology context (e.g., `82.1% MMLU-Pro (5-shot, 2026-02-21)`)
     - Training compute tier or data scale if reported
   - If no technical details are available from sources, mark `Technical details: not yet publicly disclosed.`
8. **Validate**:
   - required sections present by mode
   - no duplicate stories in same run
   - each top story has credible source(s)
   - each top story headline contains a parseable `YYYY-MM-DD` date — reject any without
9. **Render**: Telegram-safe sections, concise bullets.
   - Every referenced source must be rendered as clickable Markdown link: `[Outlet](https://...)`.
10. **Deliver**:
   - `status` mode: reply in originating chat only.
   - non-`status` modes: deliver final brief to configured output channel when present; then send a short ACK in originating chat.
   - if command originates in the configured output channel, return full response in that same chat (no DM-only detour).
   - if channel delivery fails, fall back to originating chat and mark failure reason.
11. **Persist**: run metadata + story fingerprints + suppression state.
12. **Persist stories** (non-status modes):
   - Append full story metadata to monthly archive: `workspace/outputs/summaries/ai-brief-stories-YYYY-MM.json`
   - Each entry: `{ run_id, slot, date, headline, score, model_name, architecture, sources, fingerprint }`
   - This enables trend analysis and thesis research without re-running searches.
13. **Finalize state (mandatory, last action)**:
   - write `finished_at`
   - write final `status` (`success|partial|failed`)
   - write delivery metadata + `error` field (null on success, explicit string on failure)
   - write `last_run.cost_estimate`: `{ input_tokens, output_tokens, model, estimated_usd }`
   - append run summary to `history[]` in state (keep last 20 entries): `{ run_id, slot, mode, status, started_at, finished_at, counts, cost_estimate }`
   - update `providers.brave_llm_context.last_probe_at` to current timestamp

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
3. Ranked Top Stories — per story:
   - Headline with model/product name + `YYYY-MM-DD` event date + score
   - What happened (fact bullets)
   - Why it matters
   - Technical Details (architecture, params, context window, benchmark deltas, compute tier)
   - Signal vs Hype
   - Watch next
   - Sources (clickable Markdown links)
4. Quick Hits
5. Builder / Agent Corner
6. Strategic Take
7. Tomorrow Watchlist
8. Confidence & Gaps

Example story header format:
```
### 1) Google releases Gemini 2.5 Pro (score: 0.95) — 2026-02-21
- What happened:
  - Google DeepMind released Gemini 2.5 Pro via Google AI Studio and Vertex AI
  - 2M token context window; native multimodal (text, image, audio, video, code)
- Technical Details:
  - Architecture: Sparse Mixture-of-Experts (MoE) transformer
  - Parameters: not publicly disclosed
  - Context: 2,097,152 tokens (2x vs Gemini 2.0 Pro's 1M)
  - Reasoning policy: concise final answer only (no chain-of-thought in output)
  - Benchmarks: 82.1% MMLU-Pro (5-shot, 2026-02-21); 74.3% GPQA-Diamond
  - Training compute: not disclosed
- Why it matters: ...
```

### `top5`
- Title + Top 5 + concise sources + watch-next mini-list
- Title must include explicit scope label and bounds in COT, e.g.:
  - `AI Daily Brief — Top 5 | Last 12h through 2026-02-22 19:00 (COT)`
  - `AI Daily Brief — Top 5 | Week of 2026-02-16 to 2026-02-22 (COT)`
  - `AI Daily Brief — Top 5 | Month 2026-02 (COT)`
- Each story headline MUST include `YYYY-MM-DD` event date and concrete model/product identifier when known.
- Each story MUST include a Technical Details line (abbreviated for top5 — one-liner with arch + context + key benchmark).
- Sources must be clickable Markdown links (not plain outlet names).

#### Top5 Story Format (mandatory structure per story)
Each top5 story MUST follow this exact structure — do not omit any field:
```
### {rank}) {Headline with model/product name} (score: {0.00-1.00}) — {YYYY-MM-DD}
- What happened:
  - {fact bullet 1 from sources}
  - {fact bullet 2 from sources}
- Technical Details: {architecture} | {context window} | {key benchmark or "not disclosed"}
- Why it matters: {1-2 sentence strategic significance}
- Sources: [{Outlet1}](https://url1), [{Outlet2}](https://url2)
```

#### Top5 Correct vs Incorrect Output Examples

**INCORRECT (real production failure — DO NOT produce this):**
```
1. Sam Altman Calls Out "AI Washing" | Feb 22, 2026

• OpenAI CEO warns against blame-shifting
• Sources: OpenTools, OpenAI official
```
Problems: date not ISO 8601, no score, no "What happened"/"Why it matters" structure,
no Technical Details, sources are bare names without URLs.

**CORRECT (required format):**
```
### 1) OpenAI CEO Sam Altman Warns Against "AI Washing" at India AI Summit (score: 0.72) — 2026-02-22
- What happened:
  - Sam Altman keynote at India AI Impact Summit criticized companies blaming AI for operational failures
  - Called for accountability standards separating genuine AI integration from marketing claims
- Technical Details: not applicable (policy/industry statement, no model release)
- Why it matters: Signals industry maturity pivot — largest lab CEO publicly distancing from hype cycle
- Sources: [OpenTools](https://opentools.ai/news/...), [Reuters](https://reuters.com/technology/...)
```

### `builder`
- Builder/agent tooling changes, APIs, evals, infra implications, experiments

### `watchlist`
- Current watchlist topics list
- Watchlist deltas + priority signals + unresolved unknowns

### `watchlist add <topic>` / `watchlist remove <topic>`
- Mutate `watchlist[]` in state file; confirm the updated list.
- `add`: append topic (lowercase, deduplicated).
- `remove`: remove exact match (case-insensitive). Report error if not found.

### `feedback <run_id> <1-5> [comment]`
- Record user rating (1–5 stars) for the specified run in `feedback[]` in state.
- Schema: `{ run_id, rating, comment, recorded_at }`
- Confirm: `Feedback recorded: run <run_id> rated <rating>/5.`
- Use Gemini Flash model (lightweight state write).

### `history [n]`
- Show last N runs from `history[]` in state (default n=5, max 20).
- Per entry: `run_id | slot | mode | status | started_at | counts | cost_estimate_usd`
- Use Gemini Flash model.

### `diff`
- Compare the last two completed runs in `history[]`.
- Report: new stories (in run N, not N-1), dropped stories, score movements for carried-over stories.
- Use Gemini Flash model.

### `help`
- Return the full command reference in Telegram-friendly markdown.
- Include: all modes, scope args, alias commands, `@BotName` suffix format, channel setup hint.
- Use Gemini Flash model.

### `status`
Return:
- last run + last success (morning/evening)
- candidate/cluster counts from last completed run
- last run cost estimate (`input_tokens`, `output_tokens`, `model`, `estimated_usd`)
- provider health (ok/degraded/unknown)
- provider diagnostics:
  - `provider` name
  - endpoint in use
  - key present (`yes/no`)
  - threshold mode
  - token budget for current mode
  - last probe timestamp
- **System model info (technical):**
  - Orchestrator: `gemini-2.5-flash` (google/gemini-2.5-flash)
    - Architecture: decoder-only transformer, dense attention
    - Context window: provider-managed long context
    - Role: command routing, heartbeat, status, feedback, history, diff, help
  - Synthesis: `gemini-2.5-pro` (google/gemini-2.5-pro)
    - Architecture: decoder-only transformer, dense attention
    - Context window: provider-managed long context
    - Role: AI brief retrieval clustering ranking drafting (morning/evening/top5/builder/watchlist modes)
  - Escalation: `claude-sonnet-4-6` (anthropic/claude-sonnet-4-6)
    - Architecture: decoder-only transformer, dense attention
    - Context window: 200K tokens input / 8K output
    - Role: "think harder" production-grade analysis and quality rescue
  - Manual: `claude-opus-4-6` (anthropic/claude-opus-4-6)
    - Architecture: decoder-only transformer, dense attention
    - Context window: 200K tokens input / 8K output
    - Role: explicit manual-only escalation for highest-complexity tasks
  - Ranking weights: impact=0.28, credibility=0.22, novelty=0.18, relevance=0.14, freshness=0.10, confidence=0.08
  - Brave LLM Context API: `https://api.search.brave.com/res/v1/llm/context`
  - Prompt cadence: heartbeat=55min (cache-friendly routine interval)
- Telegram delivery state (last send path/result)
- Telegram runtime snapshot when available:
  - `running`
  - `tokenSource`
  - `lastError`
  - `dmPolicy`
  - `allowFrom` count
  - interactive chats registered (from `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS`)
- active output channel target
- state file path + loaded status
- watchlist topics (current)
- recent feedback summary (last 3 ratings if present)
- expected schedule:
  - daily top5 previous calendar day: `07:00` COT
  - all other reports: on-demand only

Status truth rules:
- Do not claim "pairing blocked", "sub-agent blocked", or "gateway not paired" unless you have explicit current-run evidence.
- Explicit evidence must be one of:
  - runtime reports `running=false`, or
  - runtime `dmPolicy=pairing` with empty `allowFrom`, or
  - current-run error text explicitly contains pairing/sub-agent spawn failure.
- If explicit evidence is absent, state: `No pairing/sub-agent blocking indicator detected in current runtime signals.`
- Never infer pairing blockage purely from `last_run` being null.

## Quality Gates
- Do not present rumors as facts.
- Mark conflicting reports explicitly.
- If no credible stories: `No high-confidence AI updates in this window.`
- **Date gate (STRICT — zero tolerance):**
  - Reject any top story without a parseable `YYYY-MM-DD` event date in its headline.
  - Use `~YYYY-MM-DD (estimated)` only when source implies the date but does not state it explicitly.
  - **Vague dates are NOT acceptable.** "Feb 2026" without a day is not a valid date — you must find the actual day from sources or reject the story.
  - A date like `| Feb 2, 2026` in a "Week of Feb 16-22" brief is a hard failure. That story MUST be rejected.
- **Scope gate (STRICT — zero tolerance):**
  - In `top5` mode, reject any story whose event date falls outside the requested scope bounds.
  - "Outside scope" means: event_date < scope_start OR event_date > scope_end.
  - Do NOT include an older story just because it's important. Importance does not override scope.
  - If this leaves fewer than 5 stories, that is the correct output. Add: `Coverage limited by requested time scope.`
  - Example: scope is "Week of 2026-02-16 to 2026-02-22". A story dated 2026-02-06 is REJECTED regardless of significance.
- In `top5` mode, reject generic model claims lacking named model/product unless explicitly marked as undisclosed by sources.
- **Technical depth gate:** Each top story must include a Technical Details entry. If no technical details are publicly available, state `Technical details: not yet publicly disclosed.` — do not omit the field silently.
- **Source link gate:** Reject output with non-clickable source references. Every source must be `[Outlet](https://url)`, never a bare outlet name.
- If retrieval degraded: send partial brief and list missing coverage.
- If `BRAVE_API_KEY` is missing: report provider as unconfigured and return setup command.
- If target channel is configured but unreachable (forbidden/not admin):
  - send concise failure notice to originating chat
  - do not silently drop brief output

### Common Failure Modes (prevent these)
These are real failures observed in production. Each one MUST be prevented:

1. **Old stories in weekly brief**: Stories from Feb 2 or Feb 6 appearing in "Week of Feb 16-22".
   - Root cause: Brave query was too broad, and date gate was not applied.
   - Fix: Use date-scoped queries (see "Brave Query Construction") + apply step 6b hard gate.

2. **Vague dates**: Headlines showing "Feb 2026" instead of "2026-02-18".
   - Root cause: Date not extracted from source text.
   - Fix: Search source content for the specific date. If truly not findable, use `~YYYY-MM-DD (estimated)`.

3. **Plain-text sources**: "Sources: LLM Stats, HuMAI, MarketingProfs" with no URLs.
   - Root cause: Source URLs from Brave response were discarded.
   - Fix: Preserve URLs from `grounding.generic[].url` and render as clickable markdown.

4. **Missing Technical Details**: Stories presented without architecture/benchmark info.
   - Root cause: Technical depth gate not enforced.
   - Fix: Include the field for every story, even if content is "not yet publicly disclosed."

## Pre-Send Validation Checklist (MANDATORY — execute before delivering ANY top5 output)

Before sending the final top5 output, walk through this checklist line by line.
If ANY check fails, fix the output before sending. Do NOT send failing output.

```
CHECK 1 — DATE FORMAT: Does every story headline end with " — YYYY-MM-DD"?
  ✓ "— 2026-02-22" is valid
  ✗ "| Feb 22, 2026" is INVALID (wrong format)
  ✗ "| Feb 2026" is INVALID (no day)
  ✗ "Feb 16-22, 2026" is INVALID (range, not ISO date — pick the most significant day)
  → If any story fails: rewrite the headline with ISO 8601 date

CHECK 2 — DATE IN SCOPE: Is every story's event date within scope_start and scope_end?
  → If any story fails: remove it entirely (do not keep it)

CHECK 3 — SCORE: Does every story headline include "(score: X.XX)"?
  → If missing: compute and insert the weighted score

CHECK 4 — STRUCTURE: Does every story have ALL of these fields?
  - "What happened:" with at least 2 fact bullets
  - "Technical Details:" line (even if "not applicable" or "not disclosed")
  - "Why it matters:" with 1-2 sentences
  - "Sources:" with clickable markdown links
  → If any field is missing: add it

CHECK 5 — SOURCES: Is every source a clickable markdown link [Name](https://url)?
  ✓ [Reuters](https://reuters.com/technology/...) is valid
  ✗ "Reuters" alone is INVALID
  ✗ "Sources: OpenTools, OpenAI official" is INVALID
  → If any source lacks a URL: find the URL from Brave grounding data, or mark [Outlet](URL not available in grounding)

CHECK 6 — TITLE: Does the title include scope bounds?
  ✓ "AI Daily Brief — Top 5 | Week of 2026-02-16 to 2026-02-22 (COT)"
  ✗ "AI Daily Brief — Top 5 Stories (Week Feb 16-22, 2026)" (wrong format)
  → If wrong: reformat to match the template exactly

CHECK 7 — TECHNICAL DETAILS: Does every story have a Technical Details line?
  ✓ "Technical Details: Dense transformer | 200K context | 82.1% MMLU-Pro"
  ✓ "Technical Details: not applicable (policy announcement)"
  ✓ "Technical Details: not yet publicly disclosed"
  ✗ (field omitted entirely) is INVALID
  → If missing: add it

CHECK 8 — OUTPUT HYGIENE + FOOTER:
  - No lines starting with "Reasoning:", "Analyzing", "I will now", or "Next I will"
  - Final line is telemetry footer:
    `Tokens used: <input>/<output> - USD $<usd> / COP $<cop>`
  - Append ` - Brave api: <n>` only when Brave was used
  → If missing or malformed: fix before sending
```

Only send the output after ALL 8 checks pass.

## Efficiency Constraints
- Target runtime <60s (top5 target <45s)
- Max tool calls: 8 (top5: 6)
- Default to concise mode when signal is weak
- Avoid repeating unchanged stories from last 48h unless materially updated
- Keep retrieval under configured token budgets; do not request max context for simple factual updates
