# Tools Policy

## Tool Preference Order
1. Dedicated tools first: `read` (not `exec cat`), `web_search` (not `exec curl`), `write` (not `exec echo`).
2. Use `exec` only when no dedicated tool can perform the action.
3. For search: `web_search` for Brave queries. Never `exec curl` to Brave API directly.

## Efficiency
- Max 10 tool calls per task. Use tools for concrete value, not speculatively.
- Parallelize: if you need multiple files or searches, batch them in one parallel call.
- Never read files one-by-one when you can read them together.
- Plan all needed reads before calling. Workflow: plan → batch read → analyze → repeat only if new reads arise.

## Budget
- Subscription-covered (Codex). No per-token billing.
- Brave API has gateway-enforced caps (count=5, max_urls=6, max_tokens=1024). No manual budget tracking needed.

## Safety
- Prefer read-only. Confirm before write/delete. Keep files within workspace.
- Cite sources for web claims. Never log secrets or API keys.
- For media guidelines, see MEDIA.md.

## Forbidden
- Destructive ops (rm -rf, overwrite without backup), editing production configs/.env, force-push.
- `exec` for shell commands when a dedicated tool exists.
- Messages to third parties without approval.
- `exec curl` to call Brave or any API directly (use dedicated tools).
