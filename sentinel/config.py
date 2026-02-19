"""Sentinel configuration management."""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SentinelConfig:
    """Configuration for the Sentinel sysadmin bot."""

    # Telegram
    telegram_token: str = field(default_factory=lambda: os.getenv("SENTINEL_TELEGRAM_TOKEN", ""))
    allowed_user_ids: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("SENTINEL_ALLOWED_USERS", "").split(",") if x.strip()
    ])

    # Anthropic
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("SENTINEL_MODEL", "claude-haiku-4-5"))
    max_tokens: int = 1024

    # System
    openclaw_container_name: str = "openclaw-openclaw-gateway-1"
    log_file: str = "/var/log/sentinel/sentinel.log"
    workspace: str = os.path.expanduser("~/.sentinel")

    def validate(self) -> list[str]:
        """Return list of configuration errors."""
        errors = []
        if not self.telegram_token:
            errors.append("SENTINEL_TELEGRAM_TOKEN is not set")
        if not self.allowed_user_ids:
            errors.append("SENTINEL_ALLOWED_USERS is not set (comma-separated Telegram user IDs)")
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is not set")
        return errors
