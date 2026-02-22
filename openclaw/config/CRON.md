<!-- config-version: 2026.02.21-main-hardening -->

# Cron Job Registry

All scheduled jobs. Each defines: trigger, inputs, action, output, notification rule, cost profile.

## Design Rules
- Every job: read/analyze/notify BEFORE write/execute
- Prefer cheap model unless complexity demands escalation
- Log results to `workspace/logs/cron-job-results.md`
- On failure: log error + notify, do NOT retry automatically
- AI briefing jobs must consult `workspace/logs/ai-brief-state.json` to suppress duplicates

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

### 2. AI Daily Brief (Morning)
- **Schedule:** Daily 07:10 COT
- **Reads:** trusted AI sources from the last 12-16h, `workspace/logs/ai-brief-state.json`, optional watchlist topics
- **Action:** Retrieve, dedupe, cluster, rank, and summarize high-signal AI stories for morning consumption
- **Output:** `workspace/outputs/summaries/ai-brief-morning-YYYY-MM-DD.md`
- **Notify:** Always if >=1 credible story; otherwise send "No high-confidence AI updates in this window."
- **Model:** Sonnet (escalate only for synthesis; keep retrieval lightweight)
- **Format:** Top Stories | Quick Hits | What Changed Since Last Brief | Confidence & Gaps

### 3. AI Daily Brief (Evening)
- **Schedule:** Daily 19:00 COT
- **Reads:** trusted AI sources since morning run, `workspace/logs/ai-brief-state.json`, optional watchlist topics
- **Action:** Produce evening delta briefing focused on meaningful updates, launches, policy, and market moves
- **Output:** `workspace/outputs/summaries/ai-brief-evening-YYYY-MM-DD.md`
- **Notify:** Always if >=1 credible story; suppress unchanged repeats
- **Model:** Sonnet
- **Format:** Top Stories | Quick Hits | Updates vs Morning | Confidence & Gaps

### 4. EOD Review
- **Schedule:** Daily 20:00 COT
- **Reads:** today's brief, completed tasks, project docs
- **Action:** Compile what got done + carry forward items
- **Output:** `memory/YYYY-MM-DD.md` (daily log)
- **Notify:** Always (100-word Telegram summary)
- **Model:** Haiku
- **Format:** Completed | Deferred | Blockers | First task tomorrow

### 5. Weekly Personal Review
- **Schedule:** Sunday 20:00 COT
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
