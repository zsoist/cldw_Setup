# Heartbeat Configuration

## Schedule
- Interval: every 55 minutes (keeps Anthropic prompt cache warm at 60-min TTL)
- Active hours: 07:00 - 23:00 COT (UTC-5)
- Silent hours: 23:00 - 07:00 (no proactive messages)

## Heartbeat tasks (in order)
1. Check for unread Telegram messages that need follow-up
2. Review pending reminders/tasks due within 2 hours
3. If morning (07:00-08:00): prepare daily briefing (calendar, weather, top news in AI/tech)
4. If evening (20:00-21:00): summarize what was accomplished today

## Rules
- Heartbeat should complete in <30 seconds
- If nothing actionable, do NOT send a message (stay silent)
- Never wake Daniel during silent hours unless explicitly overridden
