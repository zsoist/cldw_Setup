# AI Daily Brief Playbook (v2)

This playbook defines the production behavior for `ai_daily_brief` in OpenClaw setup.

## Objective
- Deliver high-signal AI news twice daily.
- Avoid duplicate noise and rumor amplification.
- Keep runs stateful, auditable, and Telegram-friendly.

## Command Namespace
- `/aibrief` (auto slot)
- `/aibrief_morning`
- `/aibrief_evening`
- `/aibrief_top5`
- `/aibrief_builder`
- `/aibrief_watchlist [topics]`
- `/aibrief_status`

Rule: `/aibrief*` must never be handled by the generic personal daily briefing flow.

## Slot Rules
- Timezone: `America/Bogota`
- Morning slot: 07:10 COT
- Evening slot: 19:00 COT
- Auto slot cutoff: 13:00 COT (`<13:00` => morning)

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
- delivery status
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
