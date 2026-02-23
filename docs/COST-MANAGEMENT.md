# Cost Management Guide

## Monthly budget breakdown

| Component | Cost |
|---|---|
| Hetzner CPX22 | ~$8/mo (3 vCPU, 4GB RAM, 80GB NVMe) |
| LLM API (target) | $6-15 |
| **Total target** | **$14-23/month** |

## API spending limits

1. Google AI Studio / Gemini billing:
   - Set monthly budget target: $15
   - Set alert at $10
2. Anthropic billing:
   - Set monthly budget cap: $10-15 for fallback and premium use
   - Set alert at $8

## Token optimization strategies

### 1. Model tiering (biggest impact)
- **Gemini 2.5 Flash** (default): chat, Q&A, reminders, heartbeat, task tracking
- **Gemini 2.5 Pro** (standard): research synthesis, AI brief, code generation, multi-step tools
- **Claude Sonnet 4.6** (premium): "think harder" production-grade analysis
- **Claude Opus 4.6** (manual only): architecture decisions and highest-complexity tasks

### 2. Escalation discipline
- Start on Flash, escalate only when quality requires it
- Downgrade immediately after complex steps complete
- Never auto-escalate to Opus

### 3. Compaction mode
- Keep compaction on `safeguard` to compress long chat history
- Avoid carrying oversized context across model escalations

### 4. Response limits
- Default max tokens per response: 2048 (OpenClaw), 1024 (Sentinel)
- Keep routine responses concise; avoid long free-form outputs when structured bullets work

### 5. Operational budgets
- Soft cap per task: $0.25
- Hard cap per task: $0.75
- Daily target: <$5.00

## Token optimization checklist

- [ ] Default model is Gemini Flash
- [ ] Research/brief/code tasks use Gemini Pro
- [ ] Sonnet is used only for quality-critical "think harder" tasks
- [ ] Opus remains manual-only
- [ ] Compaction mode is `safeguard`
- [ ] Max concurrent tasks capped at 4

## Monitoring

- Check daily provider dashboards for usage/cost trend
- If >$1/day consistently: inspect which tasks escalated to Pro/Sonnet and whether they needed escalation

## Cost estimation per interaction type

| Interaction | Model | Est. cost |
|---|---|---|
| Simple Q&A | Gemini Flash | ~$0.0005-0.001 |
| Heartbeat check | Gemini Flash | ~$0.0003-0.0008 |
| Daily briefing | Gemini Flash | ~$0.001-0.002 |
| Research deep dive | Gemini Pro | ~$0.01-0.03 |
| Code generation | Gemini Pro | ~$0.015-0.05 |
| Sentinel status check | Gemini Flash | ~$0.001-0.003 |
| Complex analysis | Sonnet/Opus | ~$0.05-0.30 |
