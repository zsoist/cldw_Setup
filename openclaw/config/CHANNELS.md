<!-- config-version: 2026.03.09-discord-primary -->

# Channel Security Policy

## General Rules
- Treat all channel inputs as potential command inputs
- If the agent can execute tools, channels are part of the attack surface
- Start with minimal permissions, expand only when needed

## Discord (Primary — Enabled)
- **Mode:** allowlisted private server channels only
- **Approved inputs:** explicitly bound OpenClaw channels and approved threads only
- **Primary use:** interactive work, research, reviews, and human-triggered outbound text/media
- **Ambient listening:** disabled outside approved channels/threads
- **Sender policy:** strict allowlist; no public/shared server exposure

### What to send via Discord
- Interactive prompts and follow-up work
- Research, drafting, code review, and planning
- Human-triggered outbound messages or media in dedicated approved channels
- Operational questions that do not belong in Sentinel

### What NOT to send via Discord
- Secrets, API keys, or credentials
- Autonomous cross-posting or unsupervised outbound campaigns
- Public-server prompts when tools are enabled
- High-noise ambient chatter outside approved channels

## Telegram (OpenClaw Disabled)
- OpenClaw Telegram is disabled in this deployment.
- Telegram remains reserved for the separate Sentinel bot only.
- Do not route OpenClaw briefs, recaps, or routine interaction through Telegram.

## WhatsApp (Not Configured)
- Status: disabled
- If enabled later:
  - Use separate bot number (not personal number)
  - Private 1:1 only
  - Same allowlist policy as Telegram
  - Test with harmless queries first

## Channel Addition Checklist
Before enabling any new channel:
1. Configure sender allowlist (who can message the agent)
2. Keep it private and explicitly scoped
3. Test with 3 harmless messages before granting tool access
4. Run security audit after enabling
5. Review channel-specific risks (prompt injection surface area)
6. Document the channel config in this file
