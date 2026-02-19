"""Sentinel: Sysadmin bot for OpenClaw VPS management.

Uses Anthropic SDK with tool_use for infrastructure management.
Accessed via Telegram. Restricted to authorized users only.
"""
import json
import logging
from anthropic import Anthropic

from config import SentinelConfig
from tools import TOOLS, execute_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("sentinel")

SYSTEM_PROMPT = """You are Sentinel, a sysadmin bot managing a Hetzner CPX22 VPS.

Your responsibilities:
- Monitor system health (CPU, RAM, disk, network)
- Manage Docker containers (especially the OpenClaw gateway)
- Run security audits and report findings
- Create backups of OpenClaw configuration
- Diagnose and fix common issues
- Report status clearly and concisely

Rules:
- Only use the tools provided. Do not suggest manual SSH commands.
- If something looks dangerous or unusual, alert the user and wait for confirmation.
- Keep responses concise — this is Telegram, not an essay.
- If a restart or destructive action is requested, confirm before executing.
- Never expose secrets, tokens, or API keys in responses.
- Use bullet points for status reports.

The VPS runs:
- Ubuntu 24.04 LTS
- Docker with OpenClaw gateway container
- UFW firewall (SSH only inbound)
- fail2ban for SSH protection
- This bot (Sentinel) as a systemd service
"""


class SentinelAgent:
    """Anthropic-powered sysadmin agent with tool use."""

    def __init__(self, config: SentinelConfig):
        self.config = config
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.conversations: dict[int, list] = {}  # user_id -> message history

    def process_message(self, user_id: int, user_message: str) -> str:
        """Process a user message through Claude with tool use.

        Implements the agentic loop: send message -> get tool_use -> execute -> feed back -> repeat.
        """
        # Initialize or retrieve conversation history (keep last 10 exchanges)
        if user_id not in self.conversations:
            self.conversations[user_id] = []

        history = self.conversations[user_id]
        history.append({"role": "user", "content": user_message})

        # Trim history to last 10 exchanges (20 messages) to control token usage
        if len(history) > 20:
            history = history[-20:]
            self.conversations[user_id] = history

        # Agentic loop
        max_iterations = 5  # Prevent infinite tool loops
        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=history,
            )

            # Check if response contains tool use
            if response.stop_reason == "tool_use":
                # Process all tool calls in the response
                assistant_content = response.content
                history.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        logger.info(f"Executing tool: {block.name}({json.dumps(block.input)[:200]})")
                        result = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str)[:4000],  # Truncate
                        })

                history.append({"role": "user", "content": tool_results})
                continue  # Loop back for Claude to process results

            else:
                # Final text response
                text_response = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_response += block.text

                history.append({"role": "assistant", "content": response.content})
                self.conversations[user_id] = history
                return text_response

        return "Reached maximum tool iterations. Something may be stuck. Please try again."
