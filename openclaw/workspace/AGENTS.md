<!-- config-version: 2026.03.09-runtime-sync-v1 -->

# Workspace Agent Routing

## Direct execution rules
- News commands do not require sub-agent spawning for `/ai_daily_brief*` slash commands.
- `/brief`, `/ai_daily_brief*`, and `/expert_network_brief*` execute directly in the current lane via `news-brief/SKILL.md`.
- `/job_*` executes directly in the current lane via `job-radar/SKILL.md`.

## State
- AI brief state: `/home/node/.openclaw/workspace/logs/news-brief-state.json`
- Output channel: `config.output_channel` in the state file
