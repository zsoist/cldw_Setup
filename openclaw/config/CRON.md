<!-- config-version: 2026.02.28-news-brief-v4 -->
# Cron Jobs

## 1. AI Top 5 — Daily 07:10 COT (12:10 UTC)
`/brief ai top5` · Flash · 90s timeout · → output_channel

## 2. Expert Networks Top 5 — Daily 07:00 COT (12:00 UTC)
`/brief expert-networks top5` · Flash · 90s timeout · → output_channel

Rules: log to workspace/logs/cron-job-results.md · on failure: log + notify, no auto-retry
