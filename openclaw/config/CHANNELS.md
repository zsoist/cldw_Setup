<!-- config-version: 2026.02.21-main-hardening -->

# Channel Security Policy

## General Rules
- Treat all channel inputs as potential command inputs
- If the agent can execute tools, channels are part of the attack surface
- Start with minimal permissions, expand only when needed

## Telegram (Primary — Enabled)
- **Mode:** private DM + approved AI-brief interaction chats
- **Allowlist:** Daniel's Telegram user ID only for DM (set in env)
- **Approved channel/supergroup chats:** set `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` in env
- **Group chats:** denied by default; only explicitly approved interactive chats are allowed
- **Bot visibility:** private — not listed in public bot directories
- **Message handling:** all messages routed through agent with auth check

### What to send via Telegram
- Morning briefings (daily-briefing skill)
- Task reminders and status updates
- Short research summaries
- Decision prompts (yes/no approvals)
- Alerts (failed jobs, quota warnings, system issues via Sentinel)
- AI brief full output to configured channel target (`config.output_channel`)

### What NOT to send via Telegram
- Long code diffs or technical output
- Full research reports (send summary, store full report in workspace)
- Secrets, API keys, or credentials
- Multi-step debugging sessions (use SSH tunnel + direct access)

### Channel interaction requirements
- Bot must be admin in target channel/supergroup with permission to post.
- For command interaction in a channel context, use a supergroup/discussion chat where users can send bot commands.
- Add that chat ID to `OPENCLAW_TELEGRAM_INTERACTIVE_CHATS` and rerun rollout.

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
