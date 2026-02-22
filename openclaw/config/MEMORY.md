<!-- config-version: 2026.02.21-main-hardening -->

# Memory

## Confirmed Preferences
- Daniel is based in Bogota, Colombia (UTC-5)
- Prefers evidence-based, structured communication
- Prefers concise summaries first, then details on request
- Challenges assumptions directly — do the same back
- Optimize for cost-efficient execution

## Active Projects
- Work at Dialectica focuses on TMT consulting
- Currently studying ML at UniAndes: polynomial regression, bias-variance tradeoff, logistic regression
- Job searching in AI space — track any leads mentioned in conversation
- OpenClaw + Sentinel VPS infrastructure (Hetzner CPX22)

## Standard Operating Procedures
- Morning briefing at 07:00 COT via Telegram
- End-of-day summary at 20:00 COT — persist to `memory/YYYY-MM-DD.md`
- Weekly review Sunday 20:30 COT — persist to `memory/weekly/YYYY-WXX.md`
- GitHub backup daily at 03:00 COT (no secrets in repo)
- Heartbeat every 55 minutes during active hours to keep cache warm

## Known Constraints
- VPS: Hetzner CPX22 (4 vCPU, 8GB RAM, 80GB disk)
- Default model: Haiku (cost control). Sonnet for quality. Opus manual-only.
- Token cost target: <$5/day
- Silent hours: 23:00-07:00 COT

## Recent Lessons
- (populated by end-of-day logs — new entries go here)

---

## Daily Log System

Daily logs are stored in `memory/YYYY-MM-DD.md` with the following structure:

```markdown
# YYYY-MM-DD

## Completed
- [what was done]

## Decisions
- [what was decided and why]

## Learned
- [new facts, corrections, discoveries]

## Carry Forward
- [unfinished items for tomorrow]
```

**Growth rules:**
- End-of-day summary writes to daily log file
- Confirmed preferences discovered during the day get promoted to this MEMORY.md
- Stale entries in Active Projects get archived after 30 days of inactivity
- Weekly review compacts daily logs into weekly summary
