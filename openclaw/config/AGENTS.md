# Agents Configuration

## Default Agent
- Model: Claude Haiku 4.5 (anthropic/claude-haiku-4-5)
- Use for: general chat, Q&A, simple file operations, formatting, reminders, heartbeat
- Max tokens per response: 2048

## Escalation Rules
- Switch to Sonnet 4.5 for: code generation, skill creation, multi-step tool use, technical analysis
- Switch to Opus 4.6 for: architecture decisions, complex research synthesis (manual trigger only via /model opus)
- Always confirm before switching to Opus

## Token Guardrails
- Compaction mode: safeguard
- Max concurrent tasks: 4
- Max concurrent subagents: 4
- Heartbeat interval: 55 minutes (aligns with Anthropic 60-min cache TTL)

## Fallback chain
1. anthropic/claude-haiku-4-5 (primary)
2. anthropic/claude-sonnet-4-5 (escalation)
3. anthropic/claude-opus-4-6 (manual only)
