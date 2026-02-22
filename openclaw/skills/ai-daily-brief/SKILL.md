---
name: ai-daily-brief
description: Produce a source-grounded, stateful AI news briefing for Telegram using the dedicated /aibrief command namespace
triggers:
  - "ai daily brief"
  - "ai news brief"
  - "/aibrief"
  - "/aibrief_morning"
  - "/aibrief_evening"
  - "/aibrief_top5"
  - "/aibrief_builder"
  - "/aibrief_watchlist"
  - "/aibrief_status"
schedule: "10 7,19 * * *"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Skill

## Non-Negotiable Routing Guard
- This skill owns the `/aibrief*` namespace.
- If input starts with `/aibrief`, do **not** route to `daily-briefing` or generic personal briefing templates.
- Keep generic `/brief` behavior unchanged for non-AI personal planning workflows.

## Role
Produce a high-signal, low-noise AI news briefing for Daniel twice daily, optimized for fast Telegram reading and operational decision value.

## Supported Commands
- `/aibrief`: full brief, auto slot detect (`<13:00 COT` => morning, else evening)
- `/aibrief_morning`: force morning slot
- `/aibrief_evening`: force evening slot
- `/aibrief_top5`: compact top 5
- `/aibrief_builder`: builder/agent corner only
- `/aibrief_watchlist [topics]`: watchlist-first brief (optionally updates watchlist)
- `/aibrief_status`: operational status only (no news synthesis)

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
### Full mode (`/aibrief`, `/aibrief_morning`, `/aibrief_evening`)
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

### Top5 mode (`/aibrief_top5`)
- Title + Top 5 + concise sources + watch-next mini-list

### Builder mode (`/aibrief_builder`)
- Builder/agent tooling changes, APIs, evals, infra implications, experiments

### Watchlist mode (`/aibrief_watchlist`)
- Watchlist deltas + priority signals + unresolved unknowns

### Status mode (`/aibrief_status`)
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
