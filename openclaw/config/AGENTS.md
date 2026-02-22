<!-- config-version: 2026.02.22-ai-brief-v4 -->

# Agent Registry & Model Routing

## Sub-Agent Directory

### Researcher
- **Role:** Deep research and synthesis on any topic
- **Trigger phrases:** "research", "deep dive", "analyze", "what do we know about"
- **Use for:** market research, academic topics, tech analysis, source gathering, competitive intel
- **Do NOT use for:** creative writing, code implementation, task management
- **Input format:** topic + scope + constraints + source preferences
- **Output format:** summary → key findings → sources → implications → confidence level
- **Cost tier:** standard (Sonnet)

### Chief of Staff
- **Role:** Daily operations — briefings, task tracking, scheduling, follow-ups
- **Trigger phrases:** "morning briefing", "daily summary", "add task", "remind me", "what's pending", "todo", "priorities"
- **Use for:** morning briefings, end-of-day logs, task management, reminders, scheduling
- **Do NOT use for:** deep research, code generation, complex analysis
- **Input format:** command or time-triggered event
- **Output format:** structured bullets, checklists, or briefing sections
- **Cost tier:** cheap (Haiku)

### AI Brief Editor
- **Role:** Curate twice-daily AI news briefings with source-grounded ranking and deduplication
- **Trigger phrases:** "ai daily brief", "ai news brief", "/ai_daily_brief"
- **Use for:** AI news retrieval, clustering, ranking by impact/credibility, concise executive-style brief delivery
- **Do NOT use for:** general reminders, calendar planning, infrastructure operations, speculative rumor amplification
- **Input format:** canonical `/ai_daily_brief [morning|evening|top5|builder|watchlist|status] [optional watchlist topics]`
- **Compatibility aliases:** `/ai_daily_brief_morning`, `/ai_daily_brief_evening`, `/ai_daily_brief_top5`, `/ai_daily_brief_builder`, `/ai_daily_brief_watchlist`, `/ai_daily_brief_status`
- **Execution mode:** direct skill execution in the current lane; do not require sub-agent spawning for `/ai_daily_brief*` slash commands
- **Output format:** Full mode: Executive Snapshot → Top Stories → Quick Hits → Builder Corner → Strategic Take → Watchlist → Confidence & Gaps
- **Provider preference:** use Brave LLM Context (`/res/v1/llm/context`) for grounding with state-configured token budgets before generic web search fallback
- **Delivery routing:** read `/home/node/.openclaw/workspace/logs/ai-brief-state.json` -> `config.output_channel`; send final brief to that channel when configured, and send only ACK/status to originating chat
- **Cost tier:** standard (Sonnet)

### Command Namespace Safety
- `/ai_daily_brief` is the canonical AI brief command.
- Compatibility alias commands (`/ai_daily_brief_top5` style) must route to the same AI Brief Editor path as the canonical command.
- Generic personal briefing commands (`/brief`, "daily summary", "morning briefing") stay with **Chief of Staff**.
- Never mix AI-news synthesis into the generic daily briefing flow.

### Job Search Agent
- **Role:** Monitor and support Daniel's AI job search
- **Trigger phrases:** "job search", "applications", "job leads", "career"
- **Use for:** tracking applications, finding new postings, preparing for interviews, resume tailoring
- **Do NOT use for:** general research unrelated to career, task management
- **Input format:** search criteria, application status updates, interview prep requests
- **Output format:** ranked listings with links, application tracker updates, prep notes
- **Cost tier:** standard (Sonnet)

### Academic Assistant
- **Role:** Support ML coursework and thesis preparation
- **Trigger phrases:** "coursework", "homework", "thesis", "explain this concept", "study"
- **Use for:** ML concept explanation, problem-set help, paper review, thesis structuring
- **Do NOT use for:** writing assignments for submission, unrelated research
- **Input format:** topic or problem + course context
- **Output format:** explanation → worked examples → key takeaways → further reading
- **Cost tier:** standard (Sonnet), escalate to Opus for complex proofs or architecture

---

## Model Routing Policy

### Default: Claude Haiku 4.5 (anthropic/claude-haiku-4-5)
- General chat, Q&A, simple file operations, formatting, reminders, heartbeat
- Chief of Staff tasks (briefings, task tracking)
- Max tokens per response: 2048

### Escalation: Claude Sonnet 4.5 (anthropic/claude-sonnet-4-5)
- Research synthesis and structured reports
- Code generation, skill creation, multi-step tool use
- Technical analysis and writing quality
- Job search analysis
- Academic explanations
- AI Daily Brief clustering/ranking/synthesis
- **Downgrade back to Haiku once the complex step is complete**

### Manual only: Claude Opus 4.6 (anthropic/claude-opus-4-6)
- Architecture decisions, complex research synthesis
- Multi-step debugging, ambiguous high-stakes reasoning
- Triggered via `/model opus` — always confirm before switching
- **Downgrade immediately after the complex task finishes**

### Fallback chain
1. anthropic/claude-haiku-4-5 (primary)
2. anthropic/claude-sonnet-4-5 (escalation)
3. anthropic/claude-opus-4-6 (manual only)

## Token Guardrails
- Compaction mode: safeguard
- Max concurrent tasks: 4
- Max concurrent subagents: 4
- Heartbeat interval: 55 minutes (aligns with Anthropic 60-min cache TTL)
- Max tool calls per task: 10
- Max retries on failure: 2
