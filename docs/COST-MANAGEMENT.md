# Cost Management Guide

> Last updated: 2026-03-02

## Monthly budget breakdown

| Component | Cost |
|---|---|
| Hetzner CPX22 | ~$8/mo (3 vCPU, 4GB RAM, 80GB NVMe) |
| OpenClaw (Codex) | $0 (subscription-covered) |
| Sentinel (Flash) | ~$1-3 |
| Brave API | Free tier |
| **Total** | **~$9-11/month** |

Down from $14-23/month with Flash-only architecture.

## Model cost profile

| Model | Cost | Role |
|-------|------|------|
| OpenAI Codex (gpt-5.3-codex) | Subscription-covered | OpenClaw default (all tasks) |
| Gemini 2.5 Flash | $0.30/$2.50 per 1M tokens | Sentinel default, OpenClaw fallback |
| Gemini 2.5 Pro | $1.25/$10.00 per 1M tokens | Manual research escalation only |
| Claude Haiku 4.5 | $1.00/$5.00 per 1M tokens | Sentinel fallback only (on Google failure) |
| gpt-4o-mini, gpt-4o | API-key pricing | Configured but NOT used |

## Cost optimization strategies

### 1. Codex subscription (biggest impact)
- All OpenClaw tasks run on Codex subscription — zero per-token cost
- Chat, Q&A, heartbeat, news briefs, sub-agents, cron jobs — all $0
- Only Sentinel and Brave API have marginal costs

### 2. Sentinel cost control
- Provider: Gemini 2.5 Flash (cheapest viable model)
- max_tokens: 1500 (prevents verbose responses)
- Zero-cost commands: /status, /openclaw, /security, /backup, /cost bypass LLM entirely
- 10s Telegram long-poll timeout — zero cost at idle
- conversation_ttl: 900s (clears stale history)
- VPS-wide cost tracking: persistent cache at /var/log/sentinel/vps-cost-cache.json

### 3. Anti-spiral safeguards
- contextTokens: 65536 (hard cap prevents runaway sessions)
- contextPruning: cache-ttl 3m (evicts stale tool results)
- compaction: safeguard (auto-compacts near limits)
- SOUL.md: >100K input tokens → abort session
- SKILL.md: >100K input tokens → abort
- web_search: max 5 per session
- Brave error circuit breaker: 2 consecutive errors → stop
- Docker restart policy: on-failure:5 (prevents restart spirals)
- tools.deny: blocks expensive tools (browser, canvas, web_fetch)

### 4. System prompt efficiency
- SOUL.md: ~120 lines (includes autonomy, routing, tool efficiency)
- Sent with every API request — keep it lean
- Compaction reduces effective prompt size over long conversations

### 5. Cron cost
- 2 jobs/day, both Codex (subscription-covered) = $0/day
- Isolated sessions for clean context
- 120s timeout prevents runaway cron jobs

## Monitoring

```bash
# Sentinel cost summary (exact, from JSONL)
curl -s http://localhost:8080/health/full  # Job Radar (no LLM cost)

# Docker container resource usage
docker stats --no-stream

# Sentinel cost command (via Telegram)
/cost
```

## API billing

| Provider | Billing | Budget |
|----------|---------|--------|
| OpenAI Codex | Subscription (fixed monthly) | Covered by subscription |
| Google AI Studio | Pay-per-token | Set alert at $5/month |
| Anthropic | Not actively used | Auto-fallback disabled |
| Brave | Free tier | Gateway-enforced caps |

## What NOT to do

- Do not enable auto-fallback to Anthropic (incompatible history format, cost explosion)
- Do not switch Sentinel from Flash to a more expensive model
- Do not increase maxConcurrent above 2 (resource contention on 4GB RAM)
- Do not remove anti-spiral safeguards (contextTokens cap, session budget, tools.deny)
- Do not set Docker restart policy to `unless-stopped` (caused 54 restarts in 50 min)
