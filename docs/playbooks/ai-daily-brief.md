# AI Daily Brief Playbook

This playbook defines how the AI Daily Brief capability should run in production.

## Objective
- Deliver two concise, source-grounded AI briefings per day (morning and evening).
- Maximize signal: avoid duplicates, hype, and unverified claims.
- Keep continuity between runs using persistent state.

## Run Cadence
- Morning slot: 07:10 COT
- Evening slot: 19:00 COT
- Manual triggers:
  - `/aibrief`
  - `/aibrief_morning`
  - `/aibrief_evening`
  - `/aibrief_top5`
  - `/aibrief_watchlist <topics>`

## Source Policy
- Tier 1 (preferred):
  - official provider/lab announcements, model cards, regulatory publications
  - Reuters, Bloomberg, Financial Times, WSJ, The Information
- Tier 2 (context only):
  - social posts, newsletters, aggregators
- Do not use Tier 2 as sole evidence for top stories.

## Processing Flow
1. Retrieve stories within slot window.
2. Normalize metadata (URL/time/source labels).
3. Deduplicate and cluster related coverage.
4. Rank with weighted score:
   - impact 0.30
   - credibility 0.25
   - novelty 0.20
   - audience relevance 0.15
   - freshness 0.10
5. Summarize each cluster with 5W framing and source links.
6. Publish brief and update state file.

## Duplicate Suppression
- State file: `openclaw/workspace/logs/ai-brief-state.json`
- Before sending:
  - suppress unchanged stories already sent in the previous 48h
  - include only `update` items with material changes
- After sending:
  - persist timestamps for slot completion
  - persist fingerprints for published stories

## Quality Gate Checklist
- Every top story has at least one high-credibility source link.
- Conflicting reports are explicitly labeled.
- Opinion/rumor is separated from fact.
- Output includes `Confidence & Gaps`.
- No dead links in published output.

## Failure Handling
- If retrieval partially fails, send a reduced brief and explicitly mark missing coverage.
- If no credible stories are found:
  - send `No high-confidence AI updates in this window.`
- If state file is unreadable:
  - initialize with safe defaults and log incident in `workspace/logs/cron-job-results.md`.
