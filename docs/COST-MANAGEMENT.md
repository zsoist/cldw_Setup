# Cost Management Guide

> Last updated: 2026-02-27

## Monthly budget breakdown

| Component | Cost |
|---|---|
| Hetzner CPX22 | ~$8/mo (3 vCPU, 4GB RAM, 80GB NVMe) |
| LLM API (target) | $6-15 |
| **Total target** | **$14-23/month** |

## Current API pricing (verified 2026-02-27)

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Role |
|-------|----------------------|------------------------|------|
| Gemini 2.5 Flash | $0.30 | $2.50 | Default (everything) |
| Gemini 2.5 Pro | $1.25 | $10.00 | Escalation (complex synthesis) |
| Claude Sonnet 4.6 | $3.00 | $15.00 | Manual explicit only |
| Claude Opus 4.6 | $5.00 | $25.00 | Manual explicit only |
| Claude Haiku 4.5 | $1.00 | $5.00 | BANNED (never used) |

Sources: [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing), [platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)

## API spending limits

1. Google AI Studio / Gemini billing:
   - Set monthly budget target: $15
   - Set alert at $10
2. Anthropic billing:
   - Set monthly budget cap: $10-15 for fallback and premium use
   - Set alert at $8

## Token optimization strategies

### 1. Model tiering (biggest impact)
- **Gemini 2.5 Flash** (default): chat, Q&A, reminders, heartbeat, task tracking, sub-agents, image generation
- **Gemini 2.5 Pro** (standard): AI Daily Brief cron synthesis, research
- **Claude Sonnet 4.6** (premium): "think harder" production-grade analysis (manual only)
- **Claude Opus 4.6** (manual only): architecture decisions and highest-complexity tasks

### 2. Escalation discipline
- Start on Flash, escalate only when quality requires it
- Downgrade immediately after complex steps complete
- Never auto-escalate to Opus
- Anthropic models are manual-only (auth not auto-configured in gateway)

### 3. Compaction + context pruning
- Compaction: `safeguard` mode compresses long chat history
- Context pruning: `cache-ttl` mode evicts stale tool results after 5m
- contextTokens: 65,536 per session (reduced from 131K default and 1M overrides)
- Avoid carrying oversized context across model escalations

### 4. Response limits
- Default max tokens per response: 2048 (OpenClaw), 768 (Sentinel)
- Keep routine responses concise; avoid long free-form outputs when structured bullets work

### 5. System prompt efficiency
- SOUL.md: ~800 tokens / ~3.2KB (trimmed 63% from 8.8KB)
- Every word in SOUL.md is sent with every API request — compound cost
- No duplicate workspace files (AGENTS.md was duplicated — fixed)

### 6. Zero-cost operations
| Operation | Mechanism |
|-----------|-----------|
| Sentinel /status, /openclaw, /security, /backup | Direct tool execution, no LLM |
| Sentinel /cost | Direct file read, no LLM |
| Sentinel "hi", "thanks", "ok", "help", "ping" | Static responses, no LLM |
| Job Radar health checks (Brave) | Web search endpoint (not LLM Context) |
| Job Radar health checks (Anthropic) | Empty-messages validation (zero tokens) |
| Sentinel idle polling | HTTP long-poll to Telegram (no API cost) |

### 7. Heartbeat alignment
- Interval: 90 minutes (cache-friendly, reduced from 55m)
- Active hours: 07:00-23:00 COT only
- ~11 checks/day instead of ~17

### 8. Operational budgets
- Soft cap per task: $0.25
- Hard cap per task: $0.75
- Daily target: <$5.00

## Token optimization checklist

- [ ] Default model is Gemini Flash (agents.defaults.model.primary)
- [ ] imageModel is Gemini Flash (not Pro)
- [ ] contextTokens is 65536 (check gateway + per-session overrides)
- [ ] contextPruning is cache-ttl with 5m TTL
- [ ] Compaction mode is safeguard
- [ ] Heartbeat interval is 90m
- [ ] thinkingDefault is off
- [ ] verboseDefault is off
- [ ] No duplicate workspace files (AGENTS.md, SOUL.md)
- [ ] Sentinel slash commands bypass LLM
- [ ] Job Radar health checks are zero-cost
- [ ] Max concurrent tasks capped at 4
- [ ] Sub-agents use Flash model
- [ ] Alias skills (morning/evening/builder) use Flash
- [ ] AI Brief cron uses Pro (gateway-enforced in payload)
- [ ] ENB cron uses Flash (both AM and PM jobs)
- [ ] ENB Brave queries batched (2-3 calls, not 8 per-competitor)

## Monitoring

### Sentinel cost tracking
```bash
# View recent API calls
tail -20 /var/log/sentinel/api-usage.jsonl | python3 -m json.tool

# View cost summary
cat /var/log/sentinel/api-cost-summary.json | python3 -m json.tool

# View unified rollup (Sentinel + AI Brief)
cat /root/.openclaw/workspace/logs/api-cost-rollup.json | python3 -m json.tool

# Regenerate rollup
/root/openclaw-project/infrastructure/update-api-cost-rollup.sh
```

### Telegram /cost command
Send `/cost` to the Sentinel bot for zero-cost API usage summary. Accepts: `/cost today`, `/cost week`, `/cost month`, `/cost all`.

### Provider dashboards
- Check daily provider dashboards for usage/cost trend
- If >$1/day consistently: inspect which tasks escalated to Pro/Sonnet and whether they needed escalation

## Cost estimation per interaction type

| Interaction | Model | Est. cost |
|---|---|---|
| Simple Q&A | Gemini Flash | ~$0.0005-0.001 |
| Heartbeat check | Gemini Flash | ~$0.0003-0.0008 |
| Daily briefing | Gemini Flash | ~$0.001-0.002 |
| AI Daily Brief (cron) | Gemini Pro | ~$0.01-0.03 |
| Expert Network Brief (morning) | Gemini Flash | ~$0.005 |
| Expert Network Brief (evening delta) | Gemini Flash | ~$0.003 |
| Research deep dive | Gemini Pro | ~$0.01-0.03 |
| Code generation | Gemini Pro | ~$0.015-0.05 |
| Sentinel /status, /openclaw, etc. | None (zero-cost) | $0.00 |
| Sentinel free-text query | Gemini Flash | ~$0.001-0.003 |
| Job Radar health check | None (zero-cost) | $0.00 |
| Complex analysis | Sonnet/Opus | ~$0.05-0.30 |
