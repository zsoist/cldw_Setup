---
name: ai-daily-brief
description: Build a source-grounded AI news briefing twice daily with deduplication, ranking, citations, and duplicate suppression
triggers:
  - "ai daily brief"
  - "ai news brief"
  - "/aibrief"
  - "/aibrief_morning"
  - "/aibrief_evening"
  - "/aibrief_top5"
  - "/aibrief_watchlist"
schedule: "0 7,19 * * *"
model: sonnet
cost_tier: standard
---

# AI Daily Brief Skill

## Role
Produce a high-signal, low-noise AI news briefing for Daniel twice daily (morning and evening), with strict grounding and explicit source citation.

## Inputs
- Current local time in COT (`America/Bogota`) and slot (`morning` or `evening`)
- Time window:
  - Morning: since previous evening run or last 12-16 hours
  - Evening: since previous morning run or last 10-14 hours
- Trusted source set (Tier-1 first):
  - Primary statements: official model/provider blogs, research lab releases, model cards, regulator announcements
  - Reputable outlets: Reuters, Bloomberg, Financial Times, WSJ, The Information
  - Context-only: social posts, secondary summaries
- State file: `workspace/logs/ai-brief-state.json`
- Optional watchlist topics from state (`watchlist`)

## Pipeline
1. **Collect**
   - Retrieve AI-relevant stories only within the active window.
   - Keep source metadata: title, URL, publisher, timestamp, author (if available).
2. **Normalize**
   - Canonicalize URLs (remove obvious tracking params).
   - Normalize timestamps to UTC and COT.
3. **Deduplicate**
   - Merge obvious near-duplicates by URL/title similarity and semantic overlap.
   - Keep one canonical story per cluster based on: credibility > recency > completeness.
4. **Cluster**
   - Group by topic: frontier models, product launches, policy/regulation, enterprise adoption, security/safety, funding/M&A, research papers.
5. **Rank**
   - Compute weighted score:
     - impact 0.30
     - credibility 0.25
     - novelty 0.20
     - audience relevance 0.15
     - freshness 0.10
   - Split into `Top Stories` and `Quick Hits`.
6. **Summarize**
   - Per cluster: 2-4 bullets with who/what/when/why-it-matters.
   - Separate fact from opinion/marketing language.
   - Include 1-3 source links per top story.
7. **State update**
   - Save run metadata, story IDs/hashes, and promoted updates back to `workspace/logs/ai-brief-state.json`.
   - Mark repeated stories as `update` only when material change exists.

## Command Behavior
- `/aibrief`: auto-pick slot (`<13:00` local = morning, else evening)
- `/aibrief_morning`: force morning window
- `/aibrief_evening`: force evening window
- `/aibrief_top5`: compact output with top 5 only
- `/aibrief_watchlist <topics>`: add/update watchlist topics and run focused brief

## Output Format
Use this structure:
1. `AI Daily Brief (<slot>) — <YYYY-MM-DD HH:MM COT>`
2. `Top Stories` (ranked, each with score + why it matters + sources)
3. `Quick Hits` (short bullets)
4. `Watchlist Notes` (only if relevant)
5. `What Changed Since Last Brief` (new/update/no-change)
6. `Confidence & Gaps` (missing coverage, conflicts, unverified claims)

Length target:
- Full brief: 300-600 words
- Top5 mode: 120-220 words

## Quality Gates
- Every top story must cite at least one Tier-1 or primary source.
- If conflicting reports exist, explicitly label as `conflicting reports`.
- Never present unverified claims as facts.
- If no credible stories are found, send:
  - `No high-confidence AI updates in this window.`

## Operational Constraints
- Max tool calls: 10 per run
- Prefer Sonnet for synthesis; Haiku allowed only for lightweight rerank formatting
- Complete in <90 seconds
- Avoid repeating unchanged items from the previous run
