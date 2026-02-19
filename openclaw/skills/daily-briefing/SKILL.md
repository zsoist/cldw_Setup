---
name: daily-briefing
description: Generate a morning briefing with calendar, weather, and AI/tech news
triggers:
  - "morning briefing"
  - "daily summary"
  - "start my day"
schedule: "0 7 * * *"
---

# Daily Briefing Skill

## What it does
Generates a concise morning briefing delivered via Telegram.

## Sections (in order)
1. **Today's schedule** — Pull from calendar if connected, otherwise ask Daniel
2. **Weather** — Bogota forecast (high/low, rain probability)
3. **AI/Tech headlines** — Top 3-5 items from the past 24h relevant to AI, ML, TMT
4. **Pending tasks** — Any open reminders or follow-ups from yesterday
5. **Job search updates** — If any saved searches or applications have updates

## Format
- Total length: max 200 words
- Bullet points, no prose
- Include links for news items

## Model
- Use Haiku for this task (it's a routine aggregation, not complex reasoning)
