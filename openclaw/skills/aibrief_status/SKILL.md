---
name: aibrief_status
description: Alias command for AI Daily Brief operational status and diagnostics
model: haiku
cost_tier: cheap
---

# /aibrief_status Alias

This command returns **status only** (no news synthesis).

## Read
- `workspace/logs/ai-brief-state.json`
- latest AI brief outputs under `workspace/outputs/summaries/ai-brief-*.md` (if any)

## Output fields (required)
- Last run (run_id, slot, mode, status, start/finish)
- Last successful morning/evening timestamps
- Last run counts (candidates/clusters/included)
- Provider status (`primary`, `fallback`)
- Delivery status (message parts/result)
- State path and whether loaded successfully
- Expected schedule: `07:10` and `19:00` COT
- Next recommended action if not healthy
