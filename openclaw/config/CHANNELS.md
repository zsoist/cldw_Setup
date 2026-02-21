# Channel Security Policy

## General Rules
- Treat all channel inputs as potential command inputs
- If the agent can execute tools, channels are part of the attack surface
- Start with minimal permissions, expand only when needed

## Telegram (Primary — Enabled)
- **Mode:** private DM only (pairing mode)
- **Allowlist:** Daniel's Telegram user ID only (set in env)
- **Group chats:** DENIED — never join or respond in group chats
- **Bot visibility:** private — not listed in public bot directories
- **Message handling:** all messages routed through agent with auth check

### What to send via Telegram
- Morning briefings (daily-briefing skill)
- Task reminders and status updates
- Short research summaries
- Decision prompts (yes/no approvals)
- Alerts (failed jobs, quota warnings, system issues via Sentinel)

### What NOT to send via Telegram
- Long code diffs or technical output
- Full research reports (send summary, store full report in workspace)
- Secrets, API keys, or credentials
- Multi-step debugging sessions (use SSH tunnel + direct access)

## WhatsApp (Not Configured)
- Status: disabled
- If enabled later:
  - Use separate bot number (not personal number)
  - Private 1:1 only
  - Same allowlist policy as Telegram
  - Test with harmless queries first

## Discord (Not Configured)
- Status: disabled
- If enabled later:
  - Private server or private channel only
  - Require @mention to respond (prevent ambient listening)
  - No public/shared server exposure if agent has tool access
  - Strict sender allowlist

## Channel Addition Checklist
Before enabling any new channel:
1. Configure sender allowlist (who can message the agent)
2. Set to private/DM mode (no group chats)
3. Test with 3 harmless messages before granting tool access
4. Run security audit after enabling
5. Review channel-specific risks (prompt injection surface area)
6. Document the channel config in this file
