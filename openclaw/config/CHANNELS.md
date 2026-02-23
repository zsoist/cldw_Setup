<!-- config-version: 2026.02.23-channel-commands-v1 -->

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

### Channel Command Setup (Step-by-Step)

Three layers must all be configured for `/command` to work from a supergroup.

#### Layer 1 — Telegram Bot Privacy Mode (BotFather)

By default, Telegram bots in groups only receive commands explicitly addressed by name.
`@MangenkyoBot /ai_daily_brief status` (mention + separate command) is NOT reliably delivered.

**Option A — Disable privacy mode (recommended for a dedicated AI brief supergroup):**
1. Open Telegram → message `@BotFather`
2. Send `/setprivacy`
3. Select your OpenClaw bot username
4. Select **Disable**
5. Restart the gateway to refresh polling state:
   ```bash
   cd /root/openclaw && docker compose restart openclaw-gateway
   ```
After this, users in the approved supergroup can send `/ai_daily_brief status` (no `@botname` needed).

**Option B — Keep privacy mode ON (default):**
Users must address commands directly to the bot by name:
```
/ai_daily_brief@MangenkyoBot status
/ai_daily_brief@MangenkyoBot top5 12h
```
The `@BotName` suffix is stripped automatically during command normalization before routing.

#### Layer 2 — Discover and Register the Supergroup Chat ID

Add the bot to your supergroup, then retrieve the numeric chat ID:
```bash
TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' /root/openclaw/.env | tail -n1 | cut -d= -f2-)"
curl -s "https://api.telegram.org/bot${TG_TOKEN}/getUpdates" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for u in (data.get('result') or []):
    msg = u.get('message') or u.get('channel_post') or u.get('my_chat_member') or {}
    chat = msg.get('chat', {})
    if chat.get('id'):
        print(f'chat_id={chat[\"id\"]}  type={chat.get(\"type\")}  title={chat.get(\"title\",\"\")}')
"
```
Supergroup IDs start with `-100` (e.g., `-1001234567890`). Public channels are also negative numerics.

Register in env (replace with your actual chat ID):
```bash
cd /root/openclaw
sed -i '/^OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=/d' .env
echo 'OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=-1001234567890' >> .env
```

#### Layer 3 — Rollout and Verify

```bash
cd /root/openclaw-project
./infrastructure/vps-rollout-aibrief.sh
./infrastructure/aibrief-smoke-test.sh
```

Smoke test must pass:
- `Interactive Telegram chats registered for command invocation`
- `No active Telegram webhook (polling mode unblocked)`
- `Telegram ingest runtime is running`

Test from the registered supergroup:
```
# Privacy mode OFF (Option A):
/ai_daily_brief status

# Privacy mode ON (Option B):
/ai_daily_brief@MangenkyoBot status
```

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
