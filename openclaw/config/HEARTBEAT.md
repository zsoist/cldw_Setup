# Heartbeat
- Interval: every 180 minutes. Active hours: 07:00–23:00 COT.
- Model: openai-codex/gpt-5.3-codex (subscription-covered).
- Scope: runtime health check ONLY. No briefs, reviews, recaps, or provider probes.
- Keep `lightContext` behavior: read the minimum state needed, not full histories.
- Prefer zero-tool completion when nothing changed. Max 2 tool calls when checks are required.
- If healthy and nothing actionable: stay silent.
- If action is needed: acknowledge in <=80 chars, then only the essential next step.
