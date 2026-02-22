---
name: aibrief_builder
description: Alias command for builder-focused AI Daily Brief mode
model: sonnet
cost_tier: standard
---

# /aibrief_builder Alias

This command is an alias of `ai-daily-brief` in **builder mode**.

## Required behavior
Focus on items that affect builders/operators:
- API/runtime/tooling changes
- model behavior and eval implications
- deployment, pricing, latency, safety constraints
- practical experiments for the next 24h

Use state file: `workspace/logs/ai-brief-state.json`.

## Output
Builder / Agent Corner style summary with actionable recommendations and sources.
