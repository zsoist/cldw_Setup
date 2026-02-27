---
name: expert-network-brief-status
description: Status check for Expert Network Intelligence Brief
triggers:
  - "/expert_network_brief_status"
model: google/gemini-2.5-flash
cost_tier: cheap
---

# ENB Status Check
Tools: `read` + `message` only. Never exec scripts. Never load main expert-network-brief/SKILL.md.

## Steps
1. `read` → `/home/node/.openclaw/workspace/logs/enb-state.json`
2. `message` → formatted status

## Format
```
Expert Network Brief Status
Last run: {last_run.mode} — {last_run.status} ({finished_at})
Findings: {last_run.findings_count or "n/a"}
Competitors tracked: {config.competitors joined by ", "}
Brave provider: {brave_llm_context.status or "unknown"}
```

If state missing or last_run null: `No ENB runs recorded.`
If `last_run.status=running` and age>=900s: stale lock warning.
