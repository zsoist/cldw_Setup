# Playbook: Meeting Prep

## When
Auto-generated 12-24 hours before important meetings (cron job #7).
Also available on-demand: "prep for [meeting name]".

## Inputs
- Calendar event details (attendees, agenda, duration)
- Related docs in business/projects/active/
- Previous meeting notes (if available)
- Relevant research in docs/research/

## Output Format
```markdown
# Meeting Prep — [Meeting Name] — YYYY-MM-DD

## Objective
What should this meeting accomplish?

## Background / Context
- Key facts the attendee needs to know
- Recent developments since last meeting

## Decision(s) Needed
- [ ] Decision 1
- [ ] Decision 2

## Questions to Ask
1.
2.
3.

## Risks / Objections
- Potential pushback and how to address it

## Desired Next Step
What should happen immediately after this meeting?
```

## Rules
- Keep under 300 words
- Prioritize decisions and questions over background
- Flag if missing context blocks adequate prep
- Use Sonnet only for high-importance meetings; Haiku for routine check-ins
