<!-- config-version: 2026.03.01-codex-v2 -->

# Agent Registry & Model Routing

## Sub-Agents (delegate via task packet when appropriate)

All sub-agents run on **openai-codex/gpt-5.3-codex** (subscription-covered, gateway-enforced via `subagents.model`).

### Sub-agent behavioral contract
- Execute end-to-end within the delegated scope. Return final deliverable, not partial analysis.
- Bias to action: use sensible defaults when details are unspecified.
- No clarification questions unless truly blocked with no reasonable assumption.
- No preamble or status messages. First output must be the deliverable.
- Max 1 retry per step. On persistent failure, return error summary.

| Agent | Triggers | Model | Use for |
|-------|----------|-------|---------|
| Researcher | "research", "deep dive", "analyze" | Codex | Market research, tech analysis, source gathering |
| Chief of Staff | "briefing", "todo", "remind", "priorities" | Codex | Daily ops, task tracking, scheduling |
| News Intelligence | `/brief`, `/ai_daily_brief*`, `/expert_network_brief*`, `/enb`, "top news", "brief me", "news on" | Codex | Any news retrieval — AI, expert networks, any topic (direct in-lane) |
| Job Search | `/job_*`, "job radar" | Codex | Job tracking, applications, prep (backend-only data) |
| Academic | "coursework", "thesis", "explain concept" | Codex | ML concepts, problem sets, paper review |

## News Intelligence details
- **Role:** Topic-flexible news briefing. AI news, expert networks, or any topic via natural language.
- **Trigger phrases:** "news brief", "daily brief", "ai news", "top news", "brief me", "what's new in", "latest on", "news on", "news about", "top stories", "expert network", "competitor brief", `/brief`, `/ai_daily_brief*`, `/expert_network_brief*`, `/enb`
- **Use for:** Any news retrieval — AI, expert networks, fintech, crypto, any topic the user names
- **Do NOT use for:** general reminders, calendar, infrastructure ops, job search, deep research (use Researcher)
- **Input:** Natural language ("top ai news on Apple last month") or command (`/brief ai top5`)
- **Execution:** Direct in-lane via `news-brief` skill. No sub-agent spawn.
- **Channel context:** Strip `@BotName` suffix. Approved groups treated same as DM.
- **Output:** Ranked stories with dates + sources. Top5 ≤200 words. Deep ≤500 words.
- **State:** `/home/node/.openclaw/workspace/logs/news-brief-state.json`
- **Cost:** Subscription-covered (Codex). All modes.
- **Schedule:** AI daily 07:10 COT, ENB daily 07:00 COT

### Command Namespace Safety
- `/brief` is the canonical news command. All `/ai_daily_brief*` and `/expert_network_brief*` are backward-compatible aliases.
- Natural language normalizes to `/brief` internally before execution.
- `/job_*` commands route to Job Search Agent (unchanged).
- Generic "morning briefing" / "daily summary" stays with Chief of Staff (unchanged).

## Routing rules
- News commands do not require sub-agent spawning for `/ai_daily_brief*` slash commands.
- `/brief`, `/ai_daily_brief*`, and `/expert_network_brief*` execute directly in-lane via news-brief/SKILL.md — never spawn sub-agents.
- `/job_*` routes to job-radar skill (backend data only, no Brave).
- Generic "daily summary" / "morning briefing" → Chief of Staff (NOT News Intelligence).
- Strip `@BotName` suffix before routing. Normalize `_<mode>` suffix to space arg.

## Model chain (no auto-fallback)
1. **Codex** (gpt-5.3-codex, default) — ALL tasks: chat, Q&A, heartbeat, news briefs, job radar, research, academic. Subscription-covered. Reasoning effort: medium (interactive), high (complex tasks).
2. **Flash** (gemini-2.5-flash) — fallback ONLY if Codex is unavailable
3. **Pro** — manual research escalation only
- API-key models (openai/gpt-4o-mini, gpt-4o): DO NOT USE. Everything runs on Codex subscription.
- Haiku: NEVER used. Auto-fallback to Anthropic: DISABLED.
