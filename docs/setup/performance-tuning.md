# OpenClaw Performance Tuning

Operational practices for minimizing API costs and maximizing responsiveness. Complements `model-routing-policy.md` (which covers model selection) and the token optimization strategy in the README.

## 1. Keep System Prompt Payload Lean

OpenClaw injects the following into every API request:

- Tool list definitions
- Skill metadata (from SKILL.md files)
- Workspace/bootstrap files
- Memory pointers

Tuning parameters:

| Parameter | Purpose | Our Setting |
|-----------|---------|-------------|
| `bootstrapMaxChars` | Truncation limit per bootstrap file | Default (tune if BOOTSTRAP.md grows) |
| `bootstrapTotalMaxChars` | Total cap across all bootstrap files | Default (monitor with `/context list`) |
| SOUL.md word count | Sent with every request | < 500 words (target ~400) |

**Rule:** Every word in SOUL.md costs tokens across thousands of interactions. Keep it structured (headers, bullets), not prose.

## 2. Monitor Context Pressure

Use these commands regularly:

| Command | What It Shows |
|---------|--------------|
| `/context list` | All items in current context with token counts |
| `/context detail` | Per-item breakdown (files, tools, attachments) |

This identifies token-heavy items early. If a workspace file or tool definition is consuming disproportionate context, consider trimming or restructuring it.

## 3. Compaction and Pruning

Two mechanisms prevent context bloat:

| Mechanism | Behavior | When It Runs |
|-----------|----------|-------------|
| **Compaction** | Summarizes conversation history | Auto near context limit, or `/compact` manually |
| **Pruning** | Trims old tool results in-memory per request | Automatic per request |

Our config: `"compaction": {"mode": "safeguard"}` — auto-compacts when approaching limits.

**Practice:** Run `/compact` manually when a session feels slow or context is stale. This is especially useful after long multi-step research tasks.

## 4. Heartbeat-Cache Alignment

Anthropic's prompt cache has a **60-minute TTL**. Our heartbeat interval is **55 minutes** — just under the cache expiry.

```
Cache TTL:     |-------- 60 min --------|-------- 60 min --------|
Heartbeat:     |------ 55 min ------|------ 55 min ------|------
                     ↑ cache warm         ↑ cache warm
```

This ensures the system prompt (SOUL.md + tools + metadata) remains cached across heartbeat cycles, avoiding redundant input token charges on the static portion.

**Do not change the heartbeat interval** without understanding the cache TTL implications.

## 5. Heartbeat with Minimal Cron

With a single scheduled job, cron-driven cost is already low.

| Approach | API Calls | Cost |
|----------|-----------|------|
| 1 scheduled cron job/day | 1 | Low |
| On-demand commands for everything else | Usage-based | Controlled |

Current policy: one daily AI brief at 07:00 COT; everything else is on-demand.

## 6. Main vs Isolated Cron

Two execution modes for scheduled jobs:

| Mode | Context | Model | Use When |
|------|---------|-------|----------|
| **Main-session** | Adds to next heartbeat, shares context | Inherits session model | Cheap checks, context-dependent tasks |
| **Isolated** | Full separate turn, clean context | Can use cheaper model | Batch pipelines, independent analysis |

Our single cron job (CRON.md) defaults to main-session mode. Use isolated mode for:
- Jobs that don't need prior conversation context
- Jobs where a cheaper model (Haiku) is sufficient regardless of session model
- Batch processing that should not pollute the main session

## 7. Scheduler Reliability

OpenClaw's built-in cron has production features:

| Feature | Benefit |
|---------|---------|
| Disk persistence | Jobs survive restarts |
| Retry with backoff | Handles transient failures |
| `cron runs` command | Execution history for debugging |
| `cron status` command | Current schedule and next-fire times |

Use `cron runs` and `cron status` for operational visibility before assuming a job failed.

## 8. Web Tooling Ladder

Use the cheapest tool that works:

| Tool | Cost | Use When |
|------|------|----------|
| `brave_llm_context` | Low-to-medium | Grounded web context for AI brief and job search |
| `web_fetch` | Low | Scraping known URLs, reading docs |
| Browser automation | High | JS-heavy pages, login-required sites |

**Rule:** For AI brief and job search, use Brave LLM Context first with bounded token budgets; use browser automation only when strictly necessary.

## 9. Tuning Checklist

Periodic performance review:

- [ ] SOUL.md under 500 words (`wc -w openclaw/config/SOUL.md`)
- [ ] Run `/context list` — no single item > 20% of context
- [ ] Heartbeat interval is 55 min (cache-aligned)
- [ ] The single cron job uses main-session mode unless isolation is needed
- [ ] No browser automation for tasks achievable with Brave LLM Context
- [ ] `/compact` run on any session older than 2 hours of active use
- [ ] Response token caps enforced (2048 OpenClaw, 1024 Sentinel)
- [ ] Silent hours active (23:00-07:00 COT)
