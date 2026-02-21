"""Sentinel configuration management."""
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv


def _load_env_files() -> None:
    """Load environment variables from common deployment/local paths."""
    env_hint = os.getenv("SENTINEL_ENV_FILE")
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path("/root/openclaw/.env"),
        Path("/opt/sentinel/.env"),
    ]
    if env_hint:
        candidates.insert(0, Path(env_hint))

    seen = set()
    for path in candidates:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            load_dotenv(path, override=False)


_load_env_files()


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
