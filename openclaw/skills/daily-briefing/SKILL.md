---
name: daily-briefing
description: Generate a morning operations briefing with schedule, weather, priorities, and job-search status
triggers:
  - "morning briefing"
  - "daily summary"
  - "start my day"
schedule: "0 7 * * *"
model: haiku
cost_tier: cheap
---

# Daily Briefing Skill

## Routing Guard
- This skill handles generic personal daily planning.
- If input starts with `/ai_daily_brief`, immediately route to `ai-daily-brief`.
- Do not execute AI news synthesis here.

## Role
Morning operations agent that delivers a concise daily planning briefing to Daniel via Telegram.

## Input Requirements
- Current date and time (auto)
- Calendar data (if connected)
- Pending tasks from workspace logs and open task lists
- Active job applications from memory
- Latest AI brief pointers (status only; no deep AI story synthesis)

## Output Format
Deliver in this exact structure (max 200 words total):
1. **Today's schedule** — events from calendar, or "No calendar connected"
2. **Weather** — Bogota forecast (high/low, rain probability)
3. **Top priorities** — the 3 highest-leverage tasks for today
4. **Pending tasks** — open items sorted by priority, count included
5. **Job search updates** — application status changes, new relevant postings
6. **AI brief status** — latest `ai-daily-brief` run stamp (or "Not generated yet")

Format: bullet points with links for news items, no prose.

## Constraints
- Complete in <30 seconds
- Max 5 tool calls
- Do not duplicate full AI news headlines; delegate to `ai-daily-brief`
- Do not send if no meaningful content (send: "No major updates. Have a good day.")
- Use Haiku — this is routine aggregation, not complex reasoning

## Success Criteria
- All 6 sections present (or explicitly marked N/A)
- Total length under 200 words
- Links are valid when included
- Delivered by 07:05 COT

## Stop Conditions
- If external data is unavailable: deliver what you have and note missing section data
- If calendar unavailable: skip section, don't block on it
