# Cost Management Guide

## Monthly budget breakdown

| Component | Cost |
|---|---|
| Hetzner CPX22 | ~$8/mo (3 vCPU, 4GB RAM, 80GB NVMe) |
| LLM API (target) | $10-25 |
| **Total target** | **$18-33/month** |

## Anthropic spending limits

1. Go to console.anthropic.com -> Settings -> Billing
2. Set monthly limit: $25 (Phase 3 testing), then adjust
3. Set alert at $20

## Token optimization strategies

### 1. Model tiering (biggest impact)
- **Haiku 4.5** (default): general chat, Q&A, reminders, heartbeat, task tracking
- **Sonnet 4.5** (escalation): code generation, research synthesis, multi-step tool use
- **Opus 4.6** (manual only): architecture decisions, complex analysis

Haiku is ~60x cheaper than Opus per token. Using Haiku as default saves the most.

### 2. Prompt cache alignment
- Heartbeat interval: 55 minutes (Anthropic cache TTL is 60 minutes)
- SOUL.md is sent with every request — kept under 500 words to minimize base token cost
- Static system prompts are cached automatically by the Anthropic API

### 3. Compaction mode
- Set to "safeguard" — automatically compresses long conversations
- Prevents runaway token usage in extended chat sessions

### 4. Response limits
- Default max tokens per response: 2048 (Haiku), 1024 (Sentinel)
- Bot instructed to keep responses under 300 words
- Research skill outputs are structured (not free-form essays)

### 5. Silent hours
- No proactive messages 23:00-07:00 COT
- Heartbeat only runs during active hours
- Reduces unnecessary API calls by ~33%

## Token optimization checklist

- [ ] SOUL.md is under 500 words
- [ ] Heartbeat interval is 55 minutes (cache-aligned)
- [ ] Default model is Haiku 4.5 (not Sonnet)
- [ ] Compaction mode is "safeguard"
- [ ] Sentinel uses Haiku exclusively
- [ ] No proactive messages during silent hours (23:00-07:00)
- [ ] Max concurrent tasks capped at 4

## Monitoring

- Check daily: console.anthropic.com -> Usage
- Check weekly: total token count and cost per day trend
- If >$1/day consistently: review which tasks are using Sonnet/Opus and whether they need to

## Cost estimation per interaction type

| Interaction | Model | Est. cost |
|---|---|---|
| Simple Q&A | Haiku | ~$0.001 |
| Heartbeat check | Haiku | ~$0.0005 |
| Daily briefing | Haiku | ~$0.002 |
| Research deep dive | Sonnet | ~$0.02-0.05 |
| Code generation | Sonnet | ~$0.03-0.08 |
| Sentinel status check | Haiku | ~$0.002 |
| Complex analysis | Opus | ~$0.10-0.30 |
