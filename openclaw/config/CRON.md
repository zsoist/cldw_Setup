<!-- config-version: 2026.03.01-codex-migration -->
# Cron Jobs

## 1. AI Top 5 — Daily 07:10 COT (12:10 UTC)
`/brief ai top5` · Codex (gpt-5.3-codex) · 120s timeout · → -1003826801947

## 2. Expert Networks Top 5 — Daily 07:00 COT (12:00 UTC)
`/brief expert-networks top5` · Codex (gpt-5.3-codex) · 120s timeout · → -1003826801947

Rules: log to workspace/logs/cron-job-results.md · on failure: log + notify, no auto-retry
Model: openai-codex/gpt-5.3-codex (subscription-covered, not API tokens)
