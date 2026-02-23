<!-- config-version: 2026.02.23-single-daily-top5-v1 -->

# Cron Job Registry

Single scheduled job policy: only one automatic AI brief run is enabled.
All other actions are on-demand via Telegram commands.

## Design Rules
- Every run: read/analyze/notify BEFORE write/execute
- Log results to `workspace/logs/cron-job-results.md`
- On failure: log error + notify, do NOT retry automatically
- AI briefing job must consult `/home/node/.openclaw/workspace/logs/ai-brief-state.json`

---

### 1. AI Daily Brief Top5 (Previous Day)
- **Schedule:** Daily 06:00 COT
- **Reads:** trusted AI sources from the previous calendar day in COT (`00:00` to `23:59`), `/home/node/.openclaw/workspace/logs/ai-brief-state.json`, optional watchlist topics
- **Action:** Retrieve, dedupe, cluster, rank, and summarize Top 5 AI stories for the full previous day
- **Output:** `workspace/outputs/summaries/ai-brief-top5-previous-day-YYYY-MM-DD.md`
- **Notify:** Deliver full brief to `config.output_channel`; ACK in originating chat for DM-triggered runs
- **Model:** Sonnet
- **Format:** Top 5 (dated) | Technical Details | Source hyperlinks | Watch Next | Confidence
- **Notes:** This is the only scheduled cron job. Weekly/monthly recaps, EOD logs, health probes, and all other tasks run on-demand only.
