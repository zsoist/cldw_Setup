<!-- config-version: 2026.02.23-channel-commands-v1 -->

# Agent Registry & Model Routing

## Sub-Agent Directory

### Researcher
- **Role:** Deep research and synthesis on any topic
- **Trigger phrases:** "research", "deep dive", "analyze", "what do we know about"
- **Use for:** market research, academic topics, tech analysis, source gathering, competitive intel
- **Do NOT use for:** creative writing, code implementation, task management
- **Input format:** topic + scope + constraints + source preferences
- **Output format:** summary → key findings → sources → implications → confidence level
- **Cost tier:** standard (Gemini Pro, escalate to Sonnet)

### Chief of Staff
- **Role:** Daily operations — briefings, task tracking, scheduling, follow-ups
- **Trigger phrases:** "morning briefing", "daily summary", "add task", "remind me", "what's pending", "todo", "priorities"
- **Use for:** morning briefings, end-of-day logs, task management, reminders, scheduling
- **Do NOT use for:** deep research, code generation, complex analysis
- **Input format:** command or time-triggered event
- **Output format:** structured bullets, checklists, or briefing sections
- **Cost tier:** cheap (Flash)

### AI Brief Editor
- **Role:** Curate AI news briefings with source-grounded ranking and deduplication (single scheduled run at 07:00 COT; all other modes on-demand)
- **Trigger phrases:** "ai daily brief", "ai news brief", "top ai news", "top ai stories", "/ai_daily_brief"
- **Use for:** AI news retrieval, clustering, ranking by impact/credibility, concise executive-style brief delivery
- **Do NOT use for:** general reminders, calendar planning, infrastructure operations, speculative rumor amplification
- **Input format:** canonical `/ai_daily_brief [mode] [scope args]`
- **Modes:** `morning` | `evening` | `top5` | `builder` | `watchlist` | `status` | `feedback` | `history` | `diff` | `help`
- **Top5 scope args:** `12h` | `week` (default) | `month` | `month YYYY-MM`
- **Feedback args:** `/ai_daily_brief feedback <run_id> <1-5> [comment]`
- **Watchlist management:** `/ai_daily_brief watchlist add <topic>` | `/ai_daily_brief watchlist remove <topic>`
- **History args:** `/ai_daily_brief history [n]` — show last N runs (default 5)
- **Compatibility aliases:** `/ai_daily_brief_morning`, `/ai_daily_brief_evening`, `/ai_daily_brief_top5`, `/ai_daily_brief_builder`, `/ai_daily_brief_watchlist`, `/ai_daily_brief_status`
- **Execution mode:** direct skill execution in the current lane; do not require sub-agent spawning for `/ai_daily_brief*` slash commands
- **Channel context:** strip `@BotName` suffix before routing (e.g. `/ai_daily_brief@MangenkyoBot status` → `/ai_daily_brief status`); treat approved group/channel chats identically to DM
- **Output format:** Full mode: Executive Snapshot → Top Stories (with YYYY-MM-DD date + technical details) → Quick Hits → Builder Corner → Strategic Take → Watchlist → Confidence & Gaps
- **Provider preference:** use Brave LLM Context (`/res/v1/llm/context`) for grounding with state-configured token budgets before generic web search fallback
- **Delivery routing:** read `/home/node/.openclaw/workspace/logs/ai-brief-state.json` -> `config.output_channel`; send final brief to that channel when configured, and send only ACK/status to originating chat
- **Cost tier:** standard (Gemini Pro); `feedback`/`status`/`history`/`diff`/`help` modes use Flash

### Command Namespace Safety
- `/ai_daily_brief` is the canonical AI brief command.
- Compatibility alias commands (`/ai_daily_brief_top5` style) must route to the same AI Brief Editor path as the canonical command.
- Natural-language equivalents ("top ai news of the month/week/12h") should normalize to canonical `/ai_daily_brief top5 ...` commands before execution.
- Generic personal briefing commands (`/brief`, "daily summary", "morning briefing") stay with **Chief of Staff**.
- Never mix AI-news synthesis into the generic daily briefing flow.
- `@BotName` suffix in any `/ai_daily_brief*` command is stripped before routing — never treated as an argument.

### Job Search Agent
- **Role:** Monitor and support Daniel's AI job search
- **Trigger phrases:** "job search", "applications", "job leads", "career"
- **Use for:** tracking applications, finding new postings, preparing for interviews, resume tailoring
- **Do NOT use for:** general research unrelated to career, task management
- **Input format:** search criteria, application status updates, interview prep requests
- **Output format:** ranked listings with links, application tracker updates, prep notes
- **Cost tier:** standard (Gemini Pro, escalate to Sonnet)

### Academic Assistant
- **Role:** Support ML coursework and thesis preparation
- **Trigger phrases:** "coursework", "homework", "thesis", "explain this concept", "study"
- **Use for:** ML concept explanation, problem-set help, paper review, thesis structuring
- **Do NOT use for:** writing assignments for submission, unrelated research
- **Input format:** topic or problem + course context
- **Output format:** explanation → worked examples → key takeaways → further reading
- **Cost tier:** standard (Gemini Pro, escalate to Sonnet)

---

## Model Routing Policy

### Default: Gemini 2.5 Flash (google/gemini-2.5-flash)
- General chat, Q&A, formatting, reminders, heartbeat
- Chief of Staff tasks (briefings, task tracking)
- Max tokens per response: 2048

### Standard escalation: Gemini 2.5 Pro (google/gemini-2.5-pro)
- Research synthesis and structured reports
- AI brief synthesis/ranking and multi-step tool work
- Code generation and higher-quality technical analysis
- Job search and academic analysis requiring deeper reasoning
- **Downgrade back to Flash once the complex step is complete**

### Premium escalation: Claude Sonnet 4.6 (anthropic/claude-sonnet-4-6)
- "Think harder" requests and production-grade code
- Nuanced tradeoff analysis when Gemini Pro quality is insufficient
- **Downgrade back to Gemini Pro/Flash after the complex step is complete**

### Manual only: Claude Opus 4.6 (anthropic/claude-opus-4-6)
- Explicit `/model opus` trigger only
- Confirm before switching
- **Downgrade immediately after the complex task finishes**

### Fallback chain
1. google/gemini-2.5-flash (primary)
2. anthropic/claude-haiku-4-5 (first fallback, cross-provider)
3. anthropic/claude-sonnet-4-6 (escalation fallback)
4. anthropic/claude-opus-4-6 (manual only)

## Token Guardrails
- Compaction mode: safeguard
- Max concurrent tasks: 4
- Max concurrent subagents: 4
- Heartbeat interval: 55 minutes (cache-friendly interval for routine runs)
- Max tool calls per task: 10
- Max retries on failure: 2
