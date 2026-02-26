"""Sentinel configuration management."""
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv


def _clean_env_value(raw: str) -> str:
    """Trim whitespace and inline comments from .env style values."""
    return raw.split("#", 1)[0].strip()


def _parse_allowed_user_ids(raw: str) -> list[int]:
    """Parse comma-separated Telegram user IDs, tolerating inline comments."""
    ids: list[int] = []
    for token in raw.split(","):
        value = token.split("#", 1)[0].strip()
        if not value:
            continue
        if value.isdigit():
            ids.append(int(value))
    return ids


def _parse_positive_int(env_name: str, default: int, minimum: int = 1, maximum: int = 10_000) -> int:
    """Parse integer env var with bounds and fallback to default."""
    raw = _clean_env_value(os.getenv(env_name, ""))
    if not raw:
        return default
    if not raw.isdigit():
        return default
    value = int(raw)
    if value < minimum or value > maximum:
        return default
    return value


def _parse_bool(env_name: str, default: bool) -> bool:
    """Parse boolean env var with common truthy/falsey values."""
    raw = _clean_env_value(os.getenv(env_name, ""))
    if not raw:
        return default
    value = raw.lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_env_files() -> None:
    """Load environment variables from common deployment/local paths."""
    env_hint = os.getenv("SENTINEL_ENV_FILE")
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path("/etc/sentinel/sentinel.env"),
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
        try:
            if path.exists() and os.access(path, os.R_OK):
                load_dotenv(path, override=False)
        except OSError:
            # Best-effort loading: ignore unreadable or inaccessible env files.
            continue


_load_env_files()


@dataclass
class SentinelConfig:
    """Configuration for the Sentinel sysadmin bot."""

    # Telegram
    telegram_token: str = field(
        default_factory=lambda: _clean_env_value(os.getenv("SENTINEL_TELEGRAM_TOKEN", ""))
    )
    allowed_user_ids: list[int] = field(
        default_factory=lambda: _parse_allowed_user_ids(os.getenv("SENTINEL_ALLOWED_USERS", ""))
    )

    # Anthropic
    provider: str = field(
        default_factory=lambda: _clean_env_value(os.getenv("SENTINEL_PROVIDER", "anthropic")).lower() or "anthropic"
    )
    anthropic_api_key: str = field(
        default_factory=lambda: _clean_env_value(os.getenv("ANTHROPIC_API_KEY", ""))
    )
    google_api_key: str = field(
        default_factory=lambda: _clean_env_value(os.getenv("GEMINI_API_KEY", ""))
    )
    model: str = field(
        default_factory=lambda: _clean_env_value(os.getenv("SENTINEL_MODEL", "claude-haiku-4-5"))
    )
    max_tokens: int = 1024
    rate_limit_max_requests: int = field(
        default_factory=lambda: _parse_positive_int("SENTINEL_RATE_LIMIT_MAX_REQUESTS", 8, minimum=1, maximum=100)
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: _parse_positive_int("SENTINEL_RATE_LIMIT_WINDOW_SECONDS", 300, minimum=10, maximum=3600)
    )
    conversation_ttl_seconds: int = field(
        default_factory=lambda: _parse_positive_int("SENTINEL_CONVERSATION_TTL_SECONDS", 1800, minimum=60, maximum=86_400)
    )
    max_tool_iterations: int = field(
        default_factory=lambda: _parse_positive_int("SENTINEL_MAX_TOOL_ITERATIONS", 5, minimum=1, maximum=20)
    )
    cost_tracking_enabled: bool = field(
        default_factory=lambda: _parse_bool("SENTINEL_COST_TRACKING_ENABLED", True)
    )
    api_usage_log_file: str = field(
        default_factory=lambda: _clean_env_value(
            os.getenv("SENTINEL_API_USAGE_LOG_FILE", "/var/log/sentinel/api-usage.jsonl")
        )
    )
    api_cost_summary_file: str = field(
        default_factory=lambda: _clean_env_value(
            os.getenv("SENTINEL_API_COST_SUMMARY_FILE", "/var/log/sentinel/api-cost-summary.json")
        )
    )
    cost_retention_days: int = field(
        default_factory=lambda: _parse_positive_int("SENTINEL_COST_RETENTION_DAYS", 180, minimum=30, maximum=3650)
    )

    # System
    openclaw_container_name: str = "openclaw-openclaw-gateway-1"
    log_file: str = "/var/log/sentinel/sentinel.log"
    audit_log_file: str = "/var/log/sentinel/audit.log"
    workspace: str = os.path.expanduser("~/.sentinel")

    def validate(self) -> list[str]:
        """Return list of configuration errors."""
        errors = []
        if not self.telegram_token:
            errors.append("SENTINEL_TELEGRAM_TOKEN is not set")
        if not self.allowed_user_ids:
            errors.append("SENTINEL_ALLOWED_USERS is not set (comma-separated Telegram user IDs)")
        if self.provider not in {"anthropic", "google"}:
            errors.append("SENTINEL_PROVIDER must be 'anthropic' or 'google'")
        if self.provider == "anthropic" and not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is not set for SENTINEL_PROVIDER=anthropic")
        if self.provider == "google" and not self.google_api_key:
            errors.append("GEMINI_API_KEY is not set for SENTINEL_PROVIDER=google")
        if self.rate_limit_max_requests <= 0:
            errors.append("SENTINEL_RATE_LIMIT_MAX_REQUESTS must be > 0")
        if self.rate_limit_window_seconds <= 0:
            errors.append("SENTINEL_RATE_LIMIT_WINDOW_SECONDS must be > 0")
        if self.conversation_ttl_seconds <= 0:
            errors.append("SENTINEL_CONVERSATION_TTL_SECONDS must be > 0")
        if self.max_tool_iterations <= 0:
            errors.append("SENTINEL_MAX_TOOL_ITERATIONS must be > 0")
        if self.cost_retention_days <= 0:
            errors.append("SENTINEL_COST_RETENTION_DAYS must be > 0")
        return errors
