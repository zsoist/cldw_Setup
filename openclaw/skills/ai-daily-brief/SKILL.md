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

## Role
Produce a high-signal, low-noise AI news briefing for Daniel twice daily, optimized for Telegram readability and operational decision value.

## Inputs
- Local timezone: `America/Bogota`
- State file: `workspace/logs/ai-brief-state.json`
- Coverage window:
  - Morning: previous evening run or last 12-16h
  - Evening: previous morning run or last 10-14h
- Trusted source tiers:
  - Tier 1: official labs/vendors/model cards/regulators
  - Tier 2: Reuters/Bloomberg/FT/WSJ/The Information
  - Tier 3: secondary summaries (context only)
  - Tier 4: social posts only if corroborated

## Pipeline (deterministic first, then synthesis)
1. **Collect**: fetch AI-relevant items in coverage window.
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
10. **Persist**: run metadata + story fingerprints + suppression state.

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
- Telegram delivery state (last send path/result)
- state file path + loaded status
- expected schedule (`07:10` and `19:00` COT)

## Quality Gates
- Do not present rumors as facts.
- Mark conflicting reports explicitly.
- If no credible stories: `No high-confidence AI updates in this window.`
- If retrieval degraded: send partial brief and list missing coverage.

## Efficiency Constraints
- Target runtime <90s
- Max tool calls: 10
- Default to concise mode when signal is weak
- Avoid repeating unchanged stories from last 48h unless materially updated
