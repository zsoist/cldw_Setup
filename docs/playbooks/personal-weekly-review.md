# Playbook: Personal Weekly Review

## When
Sunday 20:30 COT (triggered by cron job #5).

## Inputs
- All daily logs from the past week (memory/YYYY-MM-DD.md)
- personal/goals.md
- personal/routines.md
- Previous weekly review (for trend comparison)

## Output Format
```markdown
# Weekly Review — YYYY-WXX

## What Progressed
- [goal/project and specific progress]

## What Stalled
- [items with no movement + why]

## Habits / Routine Compliance
- Morning routine: X/7
- Deep work blocks: X/5
- EOD reviews completed: X/7

## Top 3 Priorities Next Week
1.
2.
3.

## One Thing to Stop Doing
- [habit, distraction, or inefficiency to drop]

## Memory Updates
- [preferences or facts to promote to MEMORY.md]
```

## Rules
- Keep under 250 words
- Compare against previous week's priorities (did they get done?)
- Suggest concrete adjustments, not vague improvements
- Compact daily logs older than 30 days after review
