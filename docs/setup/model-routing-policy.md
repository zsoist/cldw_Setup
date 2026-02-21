# Model Routing Policy

Reference policy for how tasks are routed to models.
Referenced from `openclaw/config/AGENTS.md` and `openclaw/config/TOOLS.md`.

## Model Tiers

| Tier | Model | Role | Cost Factor |
|------|-------|------|-------------|
| Heartbeat | Haiku 4.5 | Cron checks, reminders, notifications | 1x |
| Default | Haiku 4.5 | Chat, Q&A, summaries, file maintenance, task tracking | 1x |
| Escalation | Sonnet 4.5 | Code, research synthesis, multi-step tools, strategic analysis | ~5x |
| Manual | Opus 4.6 | Architecture, complex reasoning, ambiguous debugging | ~60x |
| Web Search | Provider-dependent | Retrieval (separate from reasoning) | Variable |
| Deep Research | Sonnet/Opus | Expensive retrieval + synthesis (explicit only) | High |

## Routing Rules

### 1. Heartbeat / Cron (Routine)
**Use:** Haiku
- Due reminders, light system checks, "what changed today"
- Simple notifications, calendar prep checks
- Must complete in <30 seconds

### 2. Routine Assistant Work
**Use:** Haiku
- Summarize notes, organize files/docs
- Draft simple messages, generate checklists
- Transform text into markdown, task tracking
- File maintenance, daily log generation

### 3. Research & Synthesis
**Use:** Sonnet
- Multi-source research requiring cross-referencing
- Industry analysis, company research
- Job search research with competitive analysis
- TMT sector analysis for Dialectica

### 4. Complex Reasoning / High-Stakes
**Use:** Sonnet (or Opus if explicitly requested)
- Strategic planning, architecture decisions
- Important client-facing drafts
- Ambiguous debugging / root cause analysis
- Decisions affecting money, security, or reputation

### 5. Web Search
**Use:** Search endpoint + Haiku for routine, Sonnet for complex
- Prefer official docs / primary sources
- Save reusable findings to docs/research/ with date and source
- Do NOT repeatedly search the same topic if a recent local doc exists

### 6. Deep Research (Explicit Only)
**Trigger:** Only on explicit user request ("deep research", "investigate thoroughly")
- Save to docs/research/ with date + source notes
- Provide concise TL;DR + action items
- Do NOT run automatically in heartbeat or cron
- Do NOT run unless user explicitly approves cost

## Escalation Logic
1. Start with Haiku
2. Escalate to Sonnet if:
   - Result quality is inadequate on first pass
   - Task affects money, security, or reputation
   - Ambiguity remains after initial attempt
   - User explicitly asks for best-quality output
3. Use Opus only when user explicitly requests
4. Auto-downgrade back to Haiku after complex task completes

## Cost Controls
1. Heartbeat: always Haiku
2. Cron jobs: always Haiku unless complexity demands Sonnet
3. Web search: only when needed, save reusable results
4. Deep research: never automatic — explicit trigger only
5. Compact/summarize old context periodically (safeguard compaction)
6. Avoid Sonnet/Opus for repetitive tasks
7. Daily budget ceiling: <$5 (alert at $3)
