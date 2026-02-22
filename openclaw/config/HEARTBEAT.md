<!-- config-version: 2026.02.22-ai-brief-v4 -->

# Heartbeat Configuration

## Schedule
- Interval: every 55 minutes (keeps Anthropic prompt cache warm at 60-min TTL)
- Active hours: 07:00 - 23:00 COT (UTC-5)
- Silent hours: 23:00 - 07:00 (no proactive messages)

## Heartbeat tasks (in order)
1. Check for unread Telegram messages that need follow-up
2. Review pending reminders/tasks due within 2 hours
3. If morning (07:00-08:00): trigger daily planning briefing
4. If morning (07:00-07:30) and no morning AI top5 sent today: trigger `ai-daily-brief top5 12h`
5. If evening (19:00-19:30) and no evening AI top5 sent today: trigger `ai-daily-brief top5 12h`
6. If evening (20:00-21:00): run end-of-day log
7. If Sunday evening (20:00-20:20): run weekly AI top5 recap (`ai-daily-brief top5 week`)
8. If first day of month (20:00-20:20): run monthly AI top5 recap for previous month (`ai-daily-brief top5 month <previous-YYYY-MM>`)
9. If Sunday evening (20:30-21:00): run weekly review
10. If AI brief repeatedly fails, emit one concise `/ai_daily_brief status` style diagnostic (no spam)

## Rules
- Heartbeat should complete in <45 seconds
- If nothing actionable, do NOT send a message (stay silent)
- Never wake Daniel during silent hours unless explicitly overridden
- Max 7 tool calls per heartbeat cycle

## AI Daily Brief State Rules
- State file: `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- Before running AI brief:
  - verify last successful run timestamp for slot (`morning` or `evening`)
  - verify Brave provider is configured (`BRAVE_API_KEY` present) before full run
  - suppress run if already completed for current slot unless manually forced
  - suppress stories that were already sent without material updates
  - enforce strict time scope in top5 mode (`12h`, `week`, `month`)
  - if provider health is degraded, allow partial run and mark output as partial
- After successful run:
  - update slot timestamp
  - append story fingerprints and update flags
  - write output path for traceability

## End-of-Day Log (20:00 COT)
Persist the day's summary to `memory/YYYY-MM-DD.md` with this structure:
- **Completed:** tasks finished, requests handled
- **Decisions:** choices made and reasoning
- **Learned:** new facts, corrections, discoveries from today's interactions
- **Carry Forward:** unfinished items for tomorrow

After writing the daily log:
1. Promote any confirmed new preferences to `MEMORY.md` -> Confirmed Preferences
2. Update Active Projects if project status changed
3. Add any failure patterns to Recent Lessons
4. Send a concise Telegram summary (max 100 words) — do NOT send the full log

Anti-spam: if no meaningful activity occurred, write a minimal log and send:
"Quiet day. No actions required."

## Weekly Review (Sunday 20:30 COT)
Persist to `memory/weekly/YYYY-WXX.md` with this structure:
- **Week summary:** 3-5 bullet points of key accomplishments
- **Patterns:** recurring themes or requests detected
- **Metrics:** tasks completed vs. created, model usage breakdown
- **Recommendations:** 1-2 suggestions for next week
- **Memory maintenance:** flag stale MEMORY.md entries for cleanup

After writing the weekly review:
1. Compact daily logs from the past week (keep summaries, archive details)
2. Send a Telegram summary (max 150 words)

Anti-spam: if week was uneventful, send:
"Quiet week. Systems nominal. No recommendations."
