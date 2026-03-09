<!-- config-version: 2026.03.09-discord-primary -->

# Memory

## Confirmed Preferences
- Daniel is based in Bogota, Colombia (UTC-5)
- Prefers evidence-based, structured communication
- Prefers concise summaries first, then details on request
- Challenges assumptions directly — do the same back
- Optimize for cost-efficient execution

## Active Projects
- Work at TMT consulting firm (expert networks sector)
- Currently studying ML at UniAndes: polynomial regression, bias-variance tradeoff, logistic regression
- Job searching in AI space — track any leads mentioned in conversation
- OpenClaw + Sentinel VPS infrastructure (Hetzner CPX22)

## Standard Operating Procedures
- AI top stories brief is human-triggered from approved Discord channels; legacy cron delivery remains disabled
- End-of-day summaries and weekly reviews are on-demand
- GitHub backup daily at 03:00 COT (no secrets in repo)
- Heartbeat every 180 minutes during active hours (07:00-23:00 COT)

## Known Constraints
- VPS: Hetzner CPX22 (3 vCPU, 4GB RAM, 80GB disk)
- Default model: openai-codex/gpt-5.3-codex (subscription-covered). Flash fallback only.
- All models (main, subagents, heartbeat, image, skills, cron): Codex subscription.
- API-key models (gpt-4o-mini, gpt-4o): configured but NOT used as defaults.
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
