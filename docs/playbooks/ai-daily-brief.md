# AI Daily Brief Playbook (v3)

This playbook defines the production behavior for `ai_daily_brief` in OpenClaw setup.

## Objective
- Deliver high-signal AI news once daily (scheduled) and on-demand when requested.
- Avoid duplicate noise and rumor amplification.
- Keep runs stateful, auditable, and Telegram-friendly.
- Provide technical depth sufficient for an AI practitioner / MS-AI student.

## Command Namespace
- Canonical command: `/ai_daily_brief`
- Mode variants via args:
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
- Compatibility aliases:
  - `/ai_daily_brief_morning`
  - `/ai_daily_brief_evening`
  - `/ai_daily_brief_top5`
  - `/ai_daily_brief_builder`
  - `/ai_daily_brief_watchlist`
  - `/ai_daily_brief_status`
- Channel context: `/ai_daily_brief@BotName` → `@BotName` suffix stripped before routing; approved group chats treated identically to DM.

Rule: canonical command path is preferred; compatibility aliases must resolve to the same `ai-daily-brief` behavior.

## Slot Rules
- Timezone: `America/Bogota`
- Scheduled slot: 07:00 COT (Top 5, previous calendar day)
- Weekly/monthly/top5 variants are on-demand only (no automatic schedule)
- Auto slot cutoff: 13:00 COT (`<13:00` => morning)

## Provider Grounding (Brave LLM Context)
- Primary provider: Brave LLM Context API (`/res/v1/llm/context`)
- Auth: `X-Subscription-Token: ${BRAVE_API_KEY}`
- Config source:
  - `.env`: `BRAVE_API_KEY`
  - state: `config.brave_llm_context` in `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Default threshold mode: `balanced`
- Fallback behavior: if Brave is unavailable, run partial brief with fallback web search and explicit confidence downgrade.
- Brave provider health is checked during runs/on-demand status (no separate scheduled probe).

Recommended context budgets:
- `full`: `count=14`, `maximum_number_of_urls=14`, `maximum_number_of_tokens=6144`
- `top5`: `count=8`, `maximum_number_of_urls=10`, `maximum_number_of_tokens=3072`
- `builder`: `count=12`, `maximum_number_of_urls=12`, `maximum_number_of_tokens=5120`
- `watchlist`: `count=8`, `maximum_number_of_urls=8`, `maximum_number_of_tokens=2048`
- Keep per-url caps conservative for latency: `maximum_number_of_tokens_per_url <= 2048`, `maximum_number_of_snippets_per_url <= 20`
- Use adaptive Brave query fan-out:
  - query #1 always
  - query #2 only if coverage after normalization is weak
  - hard cap for `top5`: 2 Brave queries

## Telegram Output Routing
- State key: `config.output_channel` (preferred), fallback `output_channel` (legacy).
- If configured:
  - full brief is delivered to the configured channel/chat.
  - originating chat receives concise ACK/status only.
- If missing or invalid: brief falls back to originating chat.
- If send to configured target fails: fallback to originating chat and persist failure in `last_run.delivery`.

## Pipeline Stages
1. **Collect** candidates in coverage window.
2. **Normalize** title/url/publisher/timestamp fields.
3. **Deduplicate** using URL canonicalization + title similarity + state history.
4. **Cluster** by event/topic.
5. **Rank** with weighted scoring.
6. **Draft** sectioned brief — including `YYYY-MM-DD` event date and Technical Details per story.
7. **Validate** required sections/sources/dates/technical-depth.
8. **Render** mobile-readable Telegram output.
9. **Deliver** with retries and split-by-section behavior.
10. **Persist** run metadata, suppression state, story archive, cost estimate, history entry.

Latency rules:
- Do not send stage-by-stage pipeline narration unless `/ai_daily_brief status` is explicitly requested.
- Do not report "manual curation mode" for normal top5 runs.
- Top5 target runtime: `<45s`; full-mode target runtime: `<60s`.

## Ranking Policy
Default weighted score:
- impact: 0.28
- credibility: 0.22
- novelty: 0.18
- relevance: 0.14
- freshness: 0.10
- confidence: 0.08

Anti-hype penalties apply when:
- only one low-tier source exists
- benchmark/performance claims lack methodology context
- viral social claims are uncorroborated

## Source Policy
- Tier 1: official labs/vendors/model cards/regulators
- Tier 2: top-tier reporting outlets
- Tier 3: secondary summaries (context only)
- Tier 4: social posts only when corroborated

Top stories require at least one primary or Tier-1/2 source.

## Quality Gates
- **Date gate:** Each top story headline must contain a parseable `YYYY-MM-DD` date. Reject any without.
- **Technical depth gate:** Each top story must include a Technical Details section covering architecture type, parameter count (or disclosure status), context window, capability delta, and benchmark with methodology. Mark `not publicly disclosed` when unavailable.
- **Source gate:** Each top story needs at least one clickable `[Outlet](https://...)` link.
- **Scope gate (top5):** Reject any story outside requested time scope.
- **Model identity gate (top5):** Reject generic model claims without named model/product.

## Output Modes
### Full
- Title
- Executive Snapshot
- Ranked Top Stories (date, what happened, technical details, why it matters, signal-vs-hype, watch next, sources)
- Quick Hits
- Builder/Agent Corner
- Strategic Take
- Tomorrow Watchlist
- Confidence & Gaps

### Top5
- Top 5 with date + technical one-liner + sources
- Enforce requested scope exactly (`12h`, `week`, or `month`)
- Story headlines must name the concrete model/product and include `YYYY-MM-DD` date
- Every source must be a clickable markdown link `[Outlet](https://...)`

### Builder
- Builder/agent tools and infra implications only

### Watchlist
- Current watchlist topics
- Watchlist-specific updates and unknowns

### Watchlist Management
- `watchlist add <topic>`: append to `watchlist[]` in state (lowercase, deduplicated)
- `watchlist remove <topic>`: remove from `watchlist[]` (case-insensitive match)

### Feedback
- `feedback <run_id> <1-5> [comment]`: record rating in `feedback[]` in state
- Enables adaptive ranking weight tuning based on historical ratings

### History
- `history [n]`: show last N runs from `history[]` in state (default 5, max 20)
- Per entry: run_id, slot, mode, status, started_at, counts, cost_estimate_usd

### Diff
- Compare last two completed runs: new stories, dropped stories, score movements

### Help
- Return full command reference in Telegram-friendly markdown

### Status
Return run-health metadata plus technical system info:
- last run and last success
- counts (candidates/clusters/included)
- last run cost estimate (tokens + model + USD)
- provider status and diagnostics
- system model info (orchestrator, synthesis, escalation models with architecture/context specs)
- ranking weights
- delivery status
- active output channel target and interactive chats registered
- watchlist topics
- recent feedback summary
- state file path
- expected cron schedule

## State Schema (key fields)
```json
{
  "last_run": {
    "cost_estimate": { "input_tokens": 0, "output_tokens": 0, "model": "", "estimated_usd": 0.0 }
  },
  "history": [ { "run_id": "", "slot": "", "mode": "", "status": "", "started_at": "", "finished_at": "", "counts": {}, "cost_estimate": {} } ],
  "feedback": [ { "run_id": "", "rating": 0, "comment": "", "recorded_at": "" } ],
  "watchlist": [ "openai", "anthropic", "google deepmind", "meta ai", "ai regulation" ],
  "providers": {
    "brave_llm_context": { "status": "unknown", "last_check_at": null, "last_probe_at": null }
  }
}
```

## State and Duplicate Suppression
State file: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Keep `last_successful_run` per slot
- Track recent story fingerprints
- Suppress unchanged stories for at least 48h (configurable)
- Mark materially changed repeats as `update_to_prior_story=true`
- `history[]` capped at 20 entries (rolling)
- `feedback[]` unbounded (append-only)

## Story Archive (Research)
- Monthly JSON archive: `workspace/outputs/summaries/ai-brief-stories-YYYY-MM.json`
- Per story: `{ run_id, slot, date, headline, score, model_name, architecture, sources, fingerprint }`
- Enables trend analysis across time for thesis research without re-running searches.

## Failure Handling
- If partial source failure: send partial brief and list missing coverage.
- If no credible stories: send `No high-confidence AI updates in this window.`
- If state file is missing/corrupt: reinitialize schema and log event.

## Operational Commands (VPS)
- Rollout/update: `infrastructure/vps-rollout-aibrief.sh`
- Smoke test: `infrastructure/aibrief-smoke-test.sh`
- Configure output channel: `infrastructure/set-aibrief-output-channel.sh @dandailybriefAI`
- Provider sanity check:
  - `grep '^BRAVE_API_KEY=' /root/openclaw/.env`
  - `infrastructure/aibrief-smoke-test.sh` (includes Brave LLM Context probe)
