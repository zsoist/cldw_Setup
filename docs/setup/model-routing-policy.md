# Model Routing Policy

Reference policy for how tasks are routed to models.
Referenced from `openclaw/config/AGENTS.md` and `openclaw/config/TOOLS.md`.

## Model Tiers

| Tier | Model | Role | Cost Factor |
|------|-------|------|-------------|
| Default | Gemini 2.5 Flash (`google/gemini-2.5-flash`) | Chat, Q&A, heartbeat, task tracking | ~0.3x |
| Standard | Gemini 2.5 Pro (`google/gemini-2.5-pro`) | Research, AI brief synthesis, code, multi-step tools | ~2x |
| Premium | Claude Sonnet 4.6 (`anthropic/claude-sonnet-4-6`) | "Think harder", production-grade code, nuanced analysis | ~5x |
| Manual | Claude Opus 4.6 (`anthropic/claude-opus-4-6`) | Architecture, complex reasoning, ambiguous high-stakes tasks | ~60x |
| Retrieval | Brave LLM Context + web search | Source retrieval and grounding | Variable |

## Routing Rules

### 1. Heartbeat / Cron (Routine)
**Use:** Gemini Flash
- Due reminders, light system checks, and status notifications
- Must complete quickly with minimal tool usage

### 2. Routine Assistant Work
**Use:** Gemini Flash
- Summaries, formatting, reminders, task tracking, lightweight file ops

### 3. Research, AI Brief, and Multi-step Work
**Use:** Gemini Pro
- Multi-source synthesis
- AI Daily Brief ranking and drafting
- Code generation and structured technical analysis

### 4. Production-grade / "Think harder"
**Use:** Sonnet 4.6
- User explicitly requests deeper reasoning
- Gemini Pro output quality is insufficient for production decisions

### 5. Manual High-Cost Escalation
**Use:** Opus 4.6 (manual only)
- Explicit `/model opus` trigger only
- Confirm before switching and downgrade immediately after completion

## Model Chain (no automatic fallback)
1. `google/gemini-2.5-flash` (primary — default for everything)
2. `google/gemini-2.5-pro` (escalation for complex tasks)
3. `anthropic/claude-sonnet-4-6` (manual explicit only)
4. `anthropic/claude-opus-4-6` (manual explicit only)

> **Haiku is NEVER used.** Auto-fallback to Anthropic is disabled. If Gemini fails, retry then error — no silent provider switch.

## Image Routing
1. **Image Understanding (Vision):** `google/gemini-2.5-flash` (primary). Escalate to `nano-banana-pro` → Pro for complex OCR/detail.
2. **Image Generation:** Flash for drafts, `nano-banana-pro` → Pro for professional quality and text rendering.
3. Alias `nano-banana-pro` maps to `google/gemini-2.5-pro`.
4. Timeout: 60 seconds per image request.

## Video Routing
1. **Video Understanding:** `google/gemini-2.5-flash` (primary). Timeout: 120 seconds.
2. **Video Generation (Veo):** Veo 3.1 for quality, Veo 3.1 Fast for latency. Duration: 4-8 seconds. Latency: 11s-6min.

## Audio Routing
1. **Audio Understanding:** `google/gemini-2.5-flash` (primary). Timeout: 60 seconds.
2. Language: English primary, Spanish supported.

## Escalation Logic
1. Start with Flash.
2. Escalate to Pro when task complexity requires stronger synthesis/reasoning.
3. Escalate to Sonnet 4.6 when quality/reliability remains insufficient or user says "think harder".
4. Never auto-escalate to Opus.
5. Downgrade after the complex step completes.

## Cost Controls
1. Keep heartbeat and routine commands on Flash.
2. Use Pro only for research/brief/code-heavy steps.
3. Reserve Sonnet for quality-critical steps.
4. Use Opus only on explicit command.
5. Daily budget target: `<$5`.
