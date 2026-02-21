# Playbook: Daily Planning

## When
Every morning at 07:00 COT (triggered by cron job #1).

## Inputs
- Calendar events for today
- personal/goals.md (current priorities)
- personal/routines.md (scheduled blocks)
- Pending tasks / reminders
- Yesterday's EOD review (carry-forward items)

## Output Format
```markdown
# Daily Brief — YYYY-MM-DD

## Top 3 Priorities
1.
2.
3.

## Schedule
- HH:MM — [event/block]

## Prep Needed
- [meeting/event requiring preparation]

## Risks / Conflicts
- [time conflicts, missed deadlines, resource issues]

## Win Condition
If only one thing gets done today, it should be: ___
```

## Rules
- Keep under 200 words
- Flag conflicts between priorities and scheduled events
- Reference carry-forward items from yesterday's EOD
- Do not include routine items that happen every day
