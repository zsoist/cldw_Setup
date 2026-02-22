---
name: aibrief_watchlist
description: Alias command for watchlist-focused AI Daily Brief mode
model: sonnet
cost_tier: standard
---

# /aibrief_watchlist Alias

This command is an alias of `ai-daily-brief` in **watchlist mode**.

## Required behavior
- Read watchlist from `workspace/logs/ai-brief-state.json`
- If command includes topics, merge/update watchlist before run
- Return only prioritized watchlist updates and unresolved unknowns

## Output
Tomorrow Watchlist-focused brief with source links and confidence notes.
