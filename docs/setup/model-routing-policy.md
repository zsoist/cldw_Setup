# Model Routing Policy

> Last updated: 2026-03-01 (Codex-first migration)

Reference policy for how tasks are routed to models.
Referenced from `openclaw/config/AGENTS.md` and `openclaw/config/TOOLS.md`.

## Model Tiers

| Tier | Model | Role | Cost |
|------|-------|------|------|
| Default | OpenAI Codex (`openai-codex/gpt-5.3-codex`) | ALL tasks: chat, Q&A, heartbeat, news briefs, job radar, research, academic, sub-agents | Subscription-covered |
| Fallback | Gemini 2.5 Flash (`google/gemini-2.5-flash`) | Codex unavailable only | ~$0.15/M input |
| Manual | Gemini 2.5 Pro (`google/gemini-2.5-pro`) | Manual research escalation only | ~$1.25/M input |
| Sentinel | Gemini 2.5 Flash | Sentinel bot (separate service, NOT on Codex) | ~$0.15/M input |
| Retrieval | Brave LLM Context + web search | Source retrieval and grounding | Free tier |

> **API-key models (gpt-4o-mini, gpt-4o):** Configured but NOT used as defaults.
> **Haiku:** NEVER used. Auto-fallback to Anthropic: DISABLED.

## Model Chain (no automatic fallback)

1. `openai-codex/gpt-5.3-codex` (primary — subscription-covered, OAuth auth)
2. `google/gemini-2.5-flash` (fallback ONLY if Codex is unavailable)
3. `google/gemini-2.5-pro` (manual research escalation only)

## Routing Rules

### 1. Heartbeat / Cron (Routine)
**Use:** Codex (subscription-covered)
- Health checks, status notifications, news brief generation
- 180m heartbeat interval, active hours 07:00-23:00 COT
- Cron jobs: Codex, 120s timeout, isolated sessions

### 2. Routine Assistant Work
**Use:** Codex
- Summaries, formatting, reminders, task tracking, Q&A
- Bias to action: execute with defaults, no clarification questions

### 3. News Briefs + Research
**Use:** Codex
- News Brief v4: Codex, temperature 0, 20 few-shot examples
- Multi-source synthesis via Brave LLM Context API
- Sub-agents: Codex (gateway-enforced)

### 4. Manual Escalation
**Use:** Pro (manual only)
- User explicitly requests deeper research
- Downgrade immediately after completion

### 5. Sentinel (separate service)
**Use:** Gemini Flash (unchanged)
- 10 tool functions + check_api_spirals
- max_tokens: 1500, max_tool_iterations: 4
- Zero-cost commands bypass LLM entirely

## Codex Behavioral Tuning

Applied via SOUL.md and SKILL.md prompt directives:

- **Bias to action:** Execute with sensible defaults, never ask clarification questions for commands with defaults
- **No preambles:** No "Sure!", "Got it!", "Let me..." — first output must be the deliverable
- **Persistence:** Complete tasks end-to-end, don't stop at analysis
- **Tool efficiency:** Batch parallel reads, prefer dedicated tools over exec
- **Anti-looping:** Stop if stuck, report blockers instead of retrying unchanged prompts
- **<think> tag ban:** Absolute — crashes sessions, wastes 20K+ tokens

## Cost Profile

| Component | Monthly Cost |
|-----------|-------------|
| OpenClaw (Codex) | $0 (subscription-covered) |
| Sentinel (Flash) | ~$1-3 |
| Brave API | Free tier |
| VPS (Hetzner CPX22) | ~$8 |
| **Total** | **~$9-11** |

Down from $14-23/month with Flash-only architecture.
