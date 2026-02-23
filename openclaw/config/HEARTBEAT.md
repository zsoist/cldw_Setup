<!-- config-version: 2026.02.23-single-daily-top5-v1 -->

# Heartbeat Configuration

## Schedule
- Interval: every 55 minutes (cache-aligned)
- Active hours: 06:00 - 23:00 COT (UTC-5)
- Silent hours: 23:00 - 06:00 (no proactive messages)

## Heartbeat Tasks (minimal)
1. Runtime health check only (keep system responsive).
2. Do not auto-run briefs, reviews, recaps, or provider probes.
3. All non-health workflows are on-demand, except the single cron job at 06:00 COT.

## Rules
- Heartbeat should complete in <20 seconds
- If nothing actionable, stay silent
- No automatic content generation outside the single daily cron run
- Max 3 tool calls per heartbeat cycle
