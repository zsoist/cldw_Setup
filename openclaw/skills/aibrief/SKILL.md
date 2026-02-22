---
name: aibrief
description: Alias command for full AI Daily Brief with automatic morning/evening slot detection
model: sonnet
cost_tier: standard
---

# /aibrief Alias

This command is an alias of `ai-daily-brief` in **full mode** with **auto slot detection**.

## Slot
- Timezone: `America/Bogota`
- If local hour `< 13`: morning
- Else: evening

## Required behavior
- Read state: `workspace/logs/ai-brief-state.json`
- Run AI brief pipeline: collect -> normalize -> dedupe -> cluster -> rank -> summarize -> validate -> persist
- Avoid unchanged duplicates from recent runs unless materially updated

## Output
Use full format:
1. Title (slot + timestamp COT)
2. Executive Snapshot
3. Top Stories (what happened / why it matters / signal vs hype / watch next / sources)
4. Quick Hits
5. Builder / Agent Corner
6. Strategic Take
7. Tomorrow Watchlist
8. Confidence & Gaps
