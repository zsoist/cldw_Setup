# Heartbeat

- Interval: every 180 minutes
- Active hours: 07:00-23:00 COT
- Model: openai-codex/gpt-5.3-codex
- Scope: runtime health only
- Use light context only; avoid full history unless there is a real incident
- Prefer zero-tool completion when nothing changed; max 2 tool calls otherwise
- No preambles, no non-actionable recaps
- If nothing actionable: stay silent
- If action is needed: <=80 chars acknowledgement, then only the essential next step
