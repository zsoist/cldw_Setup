<!-- config-version: 2026.02.27-media-routing-v1 -->

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
- **Provider preference:** use Brave LLM Context (`/res/v1/llm/context`) for grounding as the only allowed search backend in AI brief and job-search flows
- **Delivery routing:** read `/home/node/.openclaw/workspace/logs/ai-brief-state.json` -> `config.output_channel`; send final brief to that channel when configured, and send only ACK/status to originating chat
- **Cost tier:** standard (Gemini Pro); `feedback`/`status`/`history`/`diff`/`help` modes use Flash

### Expert Network Intelligence Analyst
- **Role:** Competitive intelligence on the expert network industry
- **Trigger phrases:** "expert network brief", "competitor brief", "expert network intelligence", "/expert_network_brief", "/enb"
- **Use for:** Monitoring GLG, AlphaSights, Guidepoint, Third Bridge, Capvision, Coleman Research, Atheneum Partners, Prospex for AI capabilities, product launches, strategic moves, market expansion
- **Do NOT use for:** general AI news (use AI Brief Editor), job search, generic research
- **Input format:** `/expert_network_brief [morning|evening|status|help]`
- **Modes:** `morning` (full scan, default), `evening` (delta since morning), `status`, `help`
- **Compatibility aliases:** `/expert_network_brief_status`, `/enb`
- **Execution mode:** direct skill execution in-lane; do not require sub-agent spawning
- **Output format:** AI/Product Updates → Strategic Moves → Market Signals → Strategic Implications
- **Schedule:** AM=12:00 UTC (07:00 COT), PM=23:00 UTC (18:00 COT)
- **State file:** `/home/node/.openclaw/workspace/logs/enb-state.json`
- **Cost tier:** cheap (Flash only — structured search + summary, not deep synthesis)

### Command Namespace Safety
- `/ai_daily_brief` is the canonical AI brief command.
- Compatibility alias commands (`/ai_daily_brief_top5` style) must route to the same AI Brief Editor path as the canonical command.
- Natural-language equivalents ("top ai news of the month/week/12h") should normalize to canonical `/ai_daily_brief top5 ...` commands before execution.
- `/expert_network_brief` is the expert network competitive intelligence command. `/enb` is a shorthand alias. `/expert_network_brief_status` routes to status mode.
- `/job_*` commands (`/job_radar`, `/job_search`, `/job_why`, etc.) route to the `job-radar` skill and must use backend data only.
- Generic personal briefing commands (`/brief`, "daily summary", "morning briefing") stay with **Chief of Staff**.
- Never mix AI-news synthesis into the generic daily briefing flow or expert network brief flow.
- `@BotName` suffix in any command is stripped before routing — never treated as an argument.

### Job Search Agent
- **Role:** Monitor and support Daniel's AI job search
- **Trigger phrases:** "job search", "job radar", "applications", "job leads", "career", `/job_*`
- **Use for:** tracking applications, finding new postings, preparing for interviews, resume tailoring
- **Do NOT use for:** general research unrelated to career, task management
- **Input format:** `/job_*` command or natural-language job-search request
- **Output format:** ranked listings with links + score breakdown, tracker updates, prep notes
- **Retrieval policy:** backend (`job-radar-api`) only; backend discovery is Brave LLM Context-only
- **Model policy:** Flash default, Pro for deep explanations/trends, Sonnet only on explicit "think harder"
- **Cost tier:** cheap→standard (Flash default; selective Pro escalation)

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

### Model chain (no automatic fallback)
1. google/gemini-2.5-flash (primary — default for everything)
2. google/gemini-2.5-pro (escalation for complex tasks)
3. anthropic/claude-sonnet-4-6 (manual explicit only — never auto-triggered)
4. anthropic/claude-opus-4-6 (manual explicit only)

> **Haiku is NEVER used.** Auto-fallback to Anthropic is disabled. If Gemini is down, the system retries once then returns an error — it does NOT silently switch to Anthropic.

## Media Routing

### Image Understanding (Vision)
- Primary: `google/gemini-2.5-flash` (multimodal, cost-efficient)
- Escalation: `nano-banana-pro` alias → `google/gemini-2.5-pro` (complex OCR, detailed analysis)
- Timeout: 60 seconds per request
- Concurrency: 2 concurrent media operations

### Image Generation
- Primary: `google/gemini-2.5-flash` (quick drafts, simple requests)
- Quality: `nano-banana-pro` → `google/gemini-2.5-pro` (professional output, text in images)
- Supported resolutions: 512px, 1K, 2K, 4K
- Aspect ratios: 1:1, 16:9, 9:16, 3:2, 4:3, and more
- Prompt strategy: describe scenes naturally (subject + context + style + lighting + mood)
- All output includes SynthID watermarks

### Video Understanding
- Primary: `google/gemini-2.5-flash`
- Timeout: 120 seconds per request (videos require more processing time)
- Max payload: 50 MB

### Audio Understanding
- Primary: `google/gemini-2.5-flash`
- Timeout: 60 seconds per request
- Language: English primary, Spanish supported

## Token Guardrails
- Compaction mode: safeguard
- Max concurrent tasks: 4
- Max concurrent subagents: 4
- Heartbeat interval: 90 minutes (cost-optimized, reduced from 55 min)
- Max tool calls per task: 10
- Max retries on failure: 2
