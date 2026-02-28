<!-- config-version: 2026.02.28-news-brief-v4 -->

# Agent Registry & Model Routing

## Sub-Agents (delegate via task packet when appropriate)

| Agent | Triggers | Model | Use for |
|-------|----------|-------|---------|
| Researcher | "research", "deep dive", "analyze" | Pro | Market research, tech analysis, source gathering |
| Chief of Staff | "briefing", "todo", "remind", "priorities" | Flash | Daily ops, task tracking, scheduling |
| News Intelligence | `/brief`, `/ai_daily_brief*`, `/expert_network_brief*`, `/enb`, "top news", "brief me", "news on" | Flash | Any news retrieval — AI, expert networks, any topic (direct in-lane) |
| Job Search | `/job_*`, "job radar" | Flash→Pro | Job tracking, applications, prep (backend-only data) |
| Academic | "coursework", "thesis", "explain concept" | Pro | ML concepts, problem sets, paper review |

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
- **Cost:** Flash only. All modes.
- **Schedule:** AI daily 07:10 COT, ENB daily 07:00 COT

### Command Namespace Safety
- `/brief` is the canonical news command. All `/ai_daily_brief*` and `/expert_network_brief*` are backward-compatible aliases.
- Natural language normalizes to `/brief` internally before execution.
- `/job_*` commands route to Job Search Agent (unchanged).
- Generic "morning briefing" / "daily summary" stays with Chief of Staff (unchanged).

## Routing rules
- `/brief`, `/ai_daily_brief*`, and `/expert_network_brief*` execute directly in-lane via news-brief/SKILL.md — never spawn sub-agents.
- `/job_*` routes to job-radar skill (backend data only, Brave LLM Context for discovery).
- Generic "daily summary" / "morning briefing" → Chief of Staff (NOT News Intelligence).
- Strip `@BotName` suffix before routing. Normalize `_<mode>` suffix to space arg.

## Model chain (no auto-fallback)
1. **Flash** (default) — chat, Q&A, formatting, heartbeat, news briefs, job radar
2. **Pro** — research, code gen, academic analysis
3. **Sonnet** — manual "think harder" only, never auto-triggered
4. **Opus** — manual `/model opus` only, confirm before switching
- Haiku: NEVER used. Auto-fallback to Anthropic: DISABLED.
- Downgrade back to Flash after complex step completes.
