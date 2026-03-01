# OpenClaw Performance Tuning

> Last updated: 2026-03-01 (Codex-first migration)

Operational practices for maximizing responsiveness and preventing token spirals.

## 1. System Prompt Payload

OpenClaw injects workspace files into every API request. Keep them lean:

| File | Target | Notes |
|------|--------|-------|
| SOUL.md | < 120 lines | Sent with every request. Includes autonomy, tool efficiency, routing rules |
| AGENTS.md | < 50 lines | Sub-agent registry + behavioral contract |
| TOOLS.md | < 30 lines | Tool preference order, budget, safety |
| SKILL.md (news-brief) | ~410 lines | Only loaded when skill is triggered |

**Rule:** Every word in SOUL.md costs tokens across thousands of interactions. Structure with headers and bullets, not prose.

## 2. Context Management

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `contextTokens` | 65536 | Hard-cap context window per session (safe with Codex 266K window) |
| `contextPruning.mode` | cache-ttl | Trims old tool results per request |
| `contextPruning.ttl` | 3m | Items older than 3 minutes eligible for pruning |
| `contextPruning.keepLastAssistants` | 2 | Always keep last 2 assistant messages |
| `contextPruning.minPrunableToolChars` | 500 | Only prune tool results > 500 chars |
| `compaction.mode` | safeguard | Auto-compacts when approaching context limit |

**Practice:** Codex has first-class compaction support. The "safeguard" mode is the correct setting — it compacts automatically when needed without aggressive premature summarization.

## 3. Anti-Spiral Safeguards

Token spirals can crash sessions and waste resources. Current safeguards:

| Safeguard | Setting | Purpose |
|-----------|---------|---------|
| SOUL.md 100K budget | >100K input tokens → abort | Prevents runaway sessions |
| SKILL.md 100K budget | >100K input tokens → abort | Per-skill safety |
| web_search limit | Max 5 per session | Prevents Brave API abuse |
| Brave error circuit breaker | 2 consecutive errors → stop | Stops retrying broken API |
| Docker restart policy | on-failure:5 | Prevents restart loops (was `unless-stopped`) |
| maxConcurrent | 2 sessions | Limits parallel resource usage |
| tools.deny | browser, canvas, nodes, tts, image, web_fetch | Blocks expensive/unnecessary tools |
| thinkingDefault | off | No API-level reasoning token overhead |

## 4. Heartbeat

| Parameter | Value |
|-----------|-------|
| Interval | 180 minutes |
| Active hours | 07:00-23:00 COT |
| Model | Codex (subscription-covered) |
| Max chars | 100 |
| Cost | $0 (subscription) |

With Codex subscription, heartbeat has zero marginal cost. The 180m interval is still appropriate to avoid unnecessary context accumulation.

## 5. Cron Jobs

| Job | Schedule | Model | Timeout | Session |
|-----|----------|-------|---------|---------|
| AI Top 5 | 12:10 UTC (07:10 COT) | Codex | 120s | Isolated |
| ENB Top 5 | 12:00 UTC (07:00 COT) | Codex | 120s | Isolated |

Both use isolated sessions for clean context. Cost: $0 (subscription-covered).

## 6. Codex-Specific Optimizations

From the OpenAI Codex Prompting Guide:

- **Reasoning effort:** "medium" recommended for interactive tasks, "high/xhigh" for complex. Current: thinkingDefault=off (model reasons internally regardless)
- **Compaction:** First-class support in Codex. Our "safeguard" mode leverages this
- **Parallel tool calls:** SOUL.md and TOOLS.md instruct batch parallel reads
- **No preamble bloat:** SOUL.md bans intermediate status messages
- **Bias to action:** Execute with defaults instead of asking clarification questions

## 7. Tuning Checklist

Periodic performance review:

- [ ] SOUL.md under 120 lines
- [ ] contextTokens at 65536 (safe with Codex 266K window)
- [ ] compaction mode is "safeguard" (only valid: "default", "safeguard")
- [ ] Heartbeat interval is 180m
- [ ] Both cron jobs use isolated mode, Codex model, 120s timeout
- [ ] tools.deny includes browser, canvas, nodes, tts, image, web_fetch
- [ ] maxConcurrent is 2
- [ ] Docker restart policy is on-failure:5 (NOT unless-stopped)
- [ ] No <think> tags in any workspace file output
- [ ] Silent hours active (23:00-07:00 COT)
- [ ] Sentinel max_tokens at 1500
