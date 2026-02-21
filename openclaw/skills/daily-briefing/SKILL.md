---
name: daily-briefing
description: Generate a morning briefing with calendar, weather, and AI/tech news
triggers:
  - "morning briefing"
  - "daily summary"
  - "start my day"
schedule: "0 7 * * *"
model: haiku
cost_tier: cheap
---

# Daily Briefing Skill

## Role
Morning operations agent that delivers a concise daily briefing to Daniel via Telegram.

## Input Requirements
- Current date and time (auto)
- Calendar data (if connected)
- Pending tasks from workspace/tasks.md
- Active job applications from memory

## Output Format
Deliver in this exact structure (max 200 words total):
1. **Today's schedule** — events from calendar, or "No calendar connected"
2. **Weather** — Bogota forecast (high/low, rain probability)
3. **AI/Tech headlines** — Top 3-5 items from past 24h relevant to AI, ML, TMT
4. **Pending tasks** — open items sorted by priority, count included
5. **Job search updates** — application status changes, new relevant postings

Format: bullet points with links for news items, no prose.

## Constraints
- Complete in <30 seconds
- Max 5 tool calls (web search for news + weather)
- Do not include speculative news or unverified claims
- Do not send if no meaningful content (send: "No major updates. Have a good day.")
- Use Haiku — this is routine aggregation, not complex reasoning

## Success Criteria
- All 5 sections present (or explicitly marked N/A)
- Total length under 200 words
- Links are valid
- Delivered by 07:05 COT

## Stop Conditions
- If web search fails: deliver what you have, note "news unavailable"
- If calendar unavailable: skip section, don't block on it
