# AI Daily Brief Playbook (v2)

This playbook defines the production behavior for `ai_daily_brief` in OpenClaw setup.

## Objective
- Deliver high-signal AI news twice daily.
- Avoid duplicate noise and rumor amplification.
- Keep runs stateful, auditable, and Telegram-friendly.

## Command Namespace
- Canonical command: `/ai_daily_brief`
- Mode variants via args:
  - `/ai_daily_brief morning`
  - `/ai_daily_brief evening`
  - `/ai_daily_brief top5`
  - `/ai_daily_brief builder`
  - `/ai_daily_brief watchlist [topics]`
  - `/ai_daily_brief status`
- Compatibility aliases:
  - `/ai_daily_brief_morning`
  - `/ai_daily_brief_evening`
  - `/ai_daily_brief_top5`
  - `/ai_daily_brief_builder`
  - `/ai_daily_brief_watchlist`
  - `/ai_daily_brief_status`

Rule: canonical command path is preferred; compatibility aliases must resolve to the same `ai-daily-brief` behavior.

## Slot Rules
- Timezone: `America/Bogota`
- Morning slot: 07:10 COT
- Evening slot: 19:00 COT
- Auto slot cutoff: 13:00 COT (`<13:00` => morning)

## Provider Grounding (Brave LLM Context)
- Primary provider: Brave LLM Context API (`/res/v1/llm/context`)
- Auth: `X-Subscription-Token: ${BRAVE_API_KEY}`
- Config source:
  - `.env`: `BRAVE_API_KEY`
  - state: `config.brave_llm_context` in `openclaw/workspace/logs/ai-brief-state.json`
- Default threshold mode: `balanced`
- Fallback behavior: if Brave is unavailable, run partial brief with fallback web search and explicit confidence downgrade.

Recommended context budgets:
- `full`: `count=20`, `maximum_number_of_tokens=8192`
- `top5`: `count=12`, `maximum_number_of_tokens=4096`
- `builder`: `count=15`, `maximum_number_of_tokens=6144`
- `watchlist`: `count=10`, `maximum_number_of_tokens=3072`

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
6. **Draft** sectioned brief.
7. **Validate** required sections/sources/dupes.
8. **Render** mobile-readable Telegram output.
9. **Deliver** with retries and split-by-section behavior.
10. **Persist** run metadata and suppression state.

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

## Output Modes
### Full
- Title
- Executive Snapshot
- Ranked Top Stories (what happened, why it matters, signal-vs-hype, watch next, sources)
- Quick Hits
- Builder/Agent Corner
- Strategic Take
- Tomorrow Watchlist
- Confidence & Gaps

### Top5
- Top 5 with minimal commentary + sources

### Builder
- Builder/agent tools and infra implications only

### Watchlist
- Watchlist-specific updates and unknowns

### Status
Return run-health metadata only:
- last run and last success
- counts (candidates/clusters/included)
- provider status
- provider diagnostics (provider name, endpoint, threshold mode, key-present boolean)
- delivery status
- active output channel target
- state file path
- expected cron schedule

## State and Duplicate Suppression
State file: `openclaw/workspace/logs/ai-brief-state.json`
- Keep `last_successful_run` per slot
- Track recent story fingerprints
- Suppress unchanged stories for at least 48h (configurable)
- Mark materially changed repeats as `update_to_prior_story=true`

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
