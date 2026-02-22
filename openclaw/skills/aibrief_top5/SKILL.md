---
name: aibrief_top5
description: Alias command for compact top-5 AI Daily Brief
model: sonnet
cost_tier: standard
---

# /aibrief_top5 Alias

This command is an alias of `ai-daily-brief` in **top5 mode**.

## Required behavior
- Auto slot detection in `America/Bogota`
- Use state file: `workspace/logs/ai-brief-state.json`
- Keep only top 5 ranked stories
- Each story must include at least one credible source link

## Output
Compact top-5 briefing (120-220 words target) + sources.
