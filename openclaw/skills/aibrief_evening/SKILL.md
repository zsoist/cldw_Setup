---
name: aibrief_evening
description: Alias command for full AI Daily Brief forced to evening slot
model: sonnet
cost_tier: standard
---

# /aibrief_evening Alias

This command is an alias of `ai-daily-brief` in **full mode**, forced to **evening** slot.

## Required behavior
- Timezone: `America/Bogota`
- Slot: `evening`
- Use state file: `workspace/logs/ai-brief-state.json`
- Emphasize updates vs morning where relevant
- Suppress unchanged duplicates unless material updates exist

## Output
Full AI brief format with citations and confidence/gaps.
