<!-- config-version: 2026.02.23-channel-commands-v1 -->

# Cron Job Registry

All scheduled jobs. Each defines: trigger, inputs, action, output, notification rule, cost profile.

## Design Rules
- Every job: read/analyze/notify BEFORE write/execute
- Prefer cheap model unless complexity demands escalation
- Log results to `workspace/logs/cron-job-results.md`
- On failure: log error + notify, do NOT retry automatically
- AI briefing jobs must consult `/home/node/.openclaw/workspace/logs/ai-brief-state.json` to suppress duplicates
- AI briefing jobs must be idempotent per slot (skip if same slot already succeeded unless forced)

---

## Personal Cron Jobs

### 1. Daily Planning Brief
- **Schedule:** Daily 07:00 COT
- **Reads:** calendar (if connected), `personal/goals.md`, `personal/routines.md`, pending tasks
- **Action:** Summarize day + priorities + conflicts
- **Output:** `workspace/outputs/summaries/daily-brief-YYYY-MM-DD.md`
- **Notify:** Always (concise Telegram message)
- **Model:** Haiku (cheap)
- **Format:** Top 3 priorities | meetings/blocks | prep needed | risks | win condition for the day

### 2. AI Daily Brief Top5 (Morning 12h)
- **Schedule:** Daily 07:00 COT
- **Reads:** trusted AI sources from the previous 12h, `/home/node/.openclaw/workspace/logs/ai-brief-state.json`, optional watchlist topics
- **Action:** Retrieve, dedupe, cluster, rank, and summarize Top 5 AI stories in strict 12h scope
- **Output:** `workspace/outputs/summaries/ai-brief-top5-morning-YYYY-MM-DD.md`
- **Notify:** Deliver full brief to `config.output_channel`; ACK in originating chat for DM-triggered runs. If command originates in configured channel, return full response in that channel.
- **Model:** Sonnet (escalate only for synthesis; keep retrieval lightweight)
- **Format:** Top 5 (dated) | Source hyperlinks | Watch Next | Confidence
- **Notes:** scheduled trigger equivalent: `/ai_daily_brief top5 12h`; source lines must be clickable markdown links.

### 3. AI Daily Brief Top5 (Evening 12h)
- **Schedule:** Daily 19:00 COT
- **Reads:** trusted AI sources from the previous 12h, `/home/node/.openclaw/workspace/logs/ai-brief-state.json`, optional watchlist topics
- **Action:** Produce evening Top 5 focused on meaningful updates in strict 12h scope
- **Output:** `workspace/outputs/summaries/ai-brief-top5-evening-YYYY-MM-DD.md`
- **Notify:** Deliver full brief to `config.output_channel`; ACK in originating chat for DM-triggered runs. If command originates in configured channel, return full response in that channel.
- **Model:** Sonnet
- **Format:** Top 5 (dated) | Source hyperlinks | Watch Next | Confidence
- **Notes:** scheduled trigger equivalent: `/ai_daily_brief top5 12h`; use Brave LLM Context as primary grounding provider.

### 4. EOD Review
- **Schedule:** Daily 20:00 COT
- **Reads:** today's brief, completed tasks, project docs
- **Action:** Compile what got done + carry forward items
- **Output:** `memory/YYYY-MM-DD.md` (daily log)
- **Notify:** Always (100-word Telegram summary)
- **Model:** Haiku
- **Format:** Completed | Deferred | Blockers | First task tomorrow

### 5. Weekly Personal Review
- **Schedule:** Sunday 20:30 COT
- **Reads:** week's daily logs, `personal/goals.md`, `personal/routines.md`
- **Action:** Summarize progress + recommend 3 adjustments
- **Output:** `memory/weekly/YYYY-WXX.md`
- **Notify:** Always (150-word Telegram summary)
- **Model:** Haiku (escalate to Sonnet if strategic depth requested)
- **Format:** What progressed | What stalled | Habits compliance | Top 3 next week | One thing to stop

### 6. Calendar Prep Watch
- **Schedule:** Every 4 hours during active hours (08:00, 12:00, 16:00, 20:00)
- **Reads:** Calendar events in next 24 hours
- **Action:** Detect new/changed events, flag missing prep notes
- **Output:** `logs/cron-job-results.md` (append)
- **Notify:** Only if new event, time change, or prep missing for important meeting
- **Model:** Haiku (heartbeat-tier)

### 7. Knowledge Capture Reminder
- **Schedule:** Mon/Wed/Fri 19:00 COT
- **Reads:** recent outputs, drafts, research conversations
- **Action:** Suggest 1-3 items worth saving as reusable docs
- **Output:** `workspace/outputs/summaries/knowledge-capture-YYYY-MM-DD.md`
- **Notify:** Only if candidates worth saving exist
- **Model:** Haiku

---

## Business Cron Jobs (Work Agent)

### 8. Business Daily Snapshot
- **Schedule:** Weekdays 08:00 COT
- **Reads:** `business/goals-okrs.md`, active project docs, pipeline files
- **Action:** Summarize priorities, deadlines, blockers
- **Output:** `workspace/outputs/reports/business-daily-YYYY-MM-DD.md`
- **Notify:** Always (concise summary)
- **Model:** Haiku (escalate to Sonnet for strategic planning days)
- **Format:** Top 3 priorities | Critical deadlines | Blockers | Focus allocation | "If one thing gets done..."

### 9. Meeting Prep Generator
- **Schedule:** Hourly check during work hours (08:00-18:00)
- **Reads:** Calendar + related docs in `business/projects/active/`
- **Action:** Generate prep note for meetings within 12-24 hours
- **Output:** `workspace/outputs/summaries/meeting-prep-[slug]-YYYY-MM-DD.md`
- **Notify:** Only when prep note created or missing context blocks prep
- **Model:** Haiku for check; Sonnet for prep generation if high-importance
- **Format:** Objective | Background | Decisions needed | Questions to ask | Risks | Desired next step

### 10. Pipeline Stale Follow-Up Check
- **Schedule:** Weekdays 16:00 COT
- **Reads:** `business/projects/active/*`, job search tracker
- **Action:** Detect stale items (no update in 3+ business days)
- **Output:** `workspace/outputs/reports/stale-followups-YYYY-MM-DD.md`
- **Notify:** Only if stale items found
- **Model:** Haiku
- **Format:** Item | Last update | Risk | Suggested action | Priority

### 11. Weekly KPI / Progress Digest
- **Schedule:** Friday 17:00 COT
- **Reads:** business project files, pipeline docs, weekly metrics
- **Action:** Summarize changes and flag anomalies
- **Output:** `workspace/outputs/reports/business-weekly-YYYY-WXX.md`
- **Notify:** Always
- **Model:** Haiku (Sonnet if multi-source synthesis needed)
- **Format:** Wins | Risks | Delays | Metrics movement | Recommended interventions

### 12. Security & Ops Hygiene Reminder
- **Schedule:** Weekly (Monday 09:00 COT)
- **Reads:** `docs/security/*`, `logs/change-log.md`, cron job errors
- **Action:** Generate checklist + highlight unresolved issues
- **Output:** `workspace/outputs/reports/security-hygiene-YYYY-WXX.md`
- **Notify:** Always if issues exist; skip if clean
- **Model:** Haiku
- **Format:** Open actions | Token rotation due? | Failed jobs | New permissions added? | Next 3 checks

### 13. AI Weekly Top5 Recap
- **Schedule:** Sunday 20:00 COT
- **Reads:** trusted AI sources from current calendar week (Mon-Sun, COT), `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- **Action:** Generate weekly Top 5 recap with trend-level significance
- **Output:** `workspace/outputs/summaries/ai-brief-top5-weekly-YYYY-WXX.md`
- **Notify:** Deliver full brief to `config.output_channel`; if invoked inside channel, respond there.
- **Model:** Sonnet
- **Format:** Top 5 (week scope in title) | Why it mattered this week | Hyperlinked sources
- **Notes:** scheduled trigger equivalent: `/ai_daily_brief top5 week`

### 14. AI Monthly Top5 Recap (Previous Month)
- **Schedule:** Day 1 of every month at 20:00 COT
- **Reads:** trusted AI sources from previous calendar month, `/home/node/.openclaw/workspace/logs/ai-brief-state.json`
- **Action:** Generate monthly Top 5 recap for prior month with strategic implications
- **Output:** `workspace/outputs/summaries/ai-brief-top5-monthly-YYYY-MM.md`
- **Notify:** Deliver full brief to `config.output_channel`; if invoked inside channel, respond there.
- **Model:** Sonnet
- **Format:** Top 5 (month scope in title) | YYYY-MM-DD event dates | Technical Details per story | Strategic takeaway | Hyperlinked sources
- **Notes:** scheduled trigger equivalent: `/ai_daily_brief top5 month <previous-YYYY-MM>`

### 15. Brave Provider Health Probe
- **Schedule:** Every 6h during active hours (08:00, 14:00, 20:00 COT)
- **Reads:** `BRAVE_API_KEY` from env, `providers.brave_llm_context` from state
- **Action:** Lightweight HEAD/GET probe to Brave LLM Context endpoint; update `providers.brave_llm_context.status` and `last_probe_at` in state
- **Output:** State file mutation only (no file output)
- **Notify:** Only when provider status transitions from `ok` → `degraded` (one message, no repeat spam)
- **Model:** Haiku (lightweight, read-only check)
- **Notes:** Skip probe when `BRAVE_API_KEY` is absent. Do not run during silent hours (23:00-07:00).
