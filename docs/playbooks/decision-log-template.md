# Playbook: Decision Log

## Purpose
Record significant decisions with context so they can be reviewed later.
Prevents re-debating settled questions and documents reasoning.

## When to Log
- Any decision affecting >1 week of work
- Architecture or tool choices
- Hiring, vendor, or budget decisions
- Security or access policy changes
- Trade-offs where alternatives were considered

## Output Format
```markdown
# Decision Log

## YYYY-MM-DD — [Decision Title]
**Context:** Why this decision was needed
**Options Considered:**
1. Option A — [pros/cons]
2. Option B — [pros/cons]
3. Option C — [pros/cons]
**Decision:** [which option and why]
**Owner:** [who decided]
**Review date:** [when to revisit, if applicable]
**Status:** Active / Superseded / Reversed
```

## Rules
- Keep entries factual, not emotional
- Include what was NOT chosen and why
- Set a review date for decisions that may need revisiting
- Store in workspace/outputs/reports/ or business/projects/
