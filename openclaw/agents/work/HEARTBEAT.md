# Heartbeat — Work Agent

## Schedule
- Interval: 55 minutes (cache-aligned with main agent)
- Active hours: 08:00 - 20:00 COT (work hours only)
- Silent hours: 20:00 - 08:00 (narrower window than main agent)

## Heartbeat Tasks (in order)
1. Check for pending work tasks nearing deadline
2. If morning (08:00-09:00): check job search platforms for new relevant postings
3. If afternoon (17:00-18:00): summarize work accomplished today

## Rules
- Heartbeat should complete in <20 seconds
- If nothing actionable, stay silent — do NOT send a message
- Max 3 tool calls per heartbeat cycle
- Keep all outputs within work workspace
- Never access main agent memory or files
