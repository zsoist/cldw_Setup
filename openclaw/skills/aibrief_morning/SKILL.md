---
name: aibrief_morning
description: Alias command for full AI Daily Brief forced to morning slot
model: sonnet
cost_tier: standard
---

# /aibrief_morning Alias

This command is an alias of `ai-daily-brief` in **full mode**, forced to **morning** slot.

## Required behavior
- Timezone: `America/Bogota`
- Slot: `morning`
- Use state file: `workspace/logs/ai-brief-state.json`
- Suppress unchanged duplicates unless material updates exist
- Persist run metadata and story fingerprints back to state

## Output
Full AI brief format with citations and confidence/gaps.
