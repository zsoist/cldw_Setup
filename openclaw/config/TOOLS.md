# Tools Policy

## Rules
- Max 10 tool calls per task. Use tools for concrete value, not speculatively.
- Prefer read-only. Confirm before write/delete. Keep files within workspace.
- Budget: soft $0.25/task, hard $0.75/task, daily <$5.00.
- Cite sources for web claims. Never log secrets or API keys.
- For media guidelines, see MEDIA.md.

## Forbidden
- Destructive ops (rm -rf, overwrite without backup), shell commands, editing production configs/.env, force-push, messages to third parties without approval.
