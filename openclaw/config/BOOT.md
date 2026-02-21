# Boot — Startup Behavior

Run these checks every time the gateway/service starts.
This is NOT first-run behavior (see BOOTSTRAP.md for that).

## Startup Sequence
1. Confirm gateway process is healthy (port 18789 responding)
2. Verify model routing config is readable (AGENTS.md parsed)
3. Verify cron jobs are loaded (CRON.md parsed)
4. Verify heartbeat config is active (HEARTBEAT.md parsed)
5. Confirm Telegram channel connection is live
6. Check workspace directories exist (personal/, business/, outputs/, logs/)

## Startup Safety
- Do NOT run heavy jobs on boot
- Do NOT run deep research on boot
- Do NOT modify configs automatically on boot
- Do NOT send proactive messages until first heartbeat cycle

## On Failure
- If any check fails: log to logs/change-log.md with timestamp
- If gateway HTTP fails: notify via Telegram if channel is available
- If model config unreadable: fall back to Haiku defaults, log warning
- Do NOT attempt auto-repair of config files

## Status Report
Produce a short startup summary only if explicitly configured or requested.
Format: one-line per check, PASS/FAIL status, total boot time.
