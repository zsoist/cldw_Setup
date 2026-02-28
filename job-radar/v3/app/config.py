import os


class Config:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://jobagent:jobagent@job-radar-db:5432/jobradar")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHANNEL_ID: int = int(os.getenv("TELEGRAM_CHANNEL_ID", "-1003826801947"))
    TELEGRAM_OWNER_CHAT_ID: int = int(os.getenv("TELEGRAM_OWNER_CHAT_ID", "0"))
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    BRAVE_RESULTS_PER_QUERY: int = int(os.getenv("BRAVE_RESULTS_PER_QUERY", "10"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ENRICHMENT_MODEL: str = os.getenv("ENRICHMENT_MODEL", "gemini-2.5-flash")
    JOB_MAX_AGE_DAYS: int = int(os.getenv("JOB_MAX_AGE_DAYS", "21"))
    JOB_STALE_WARNING_DAYS: int = int(os.getenv("JOB_STALE_WARNING_DAYS", "14"))
    DIGEST_MIN_COMPOSITE: int = int(os.getenv("DIGEST_MIN_COMPOSITE", "45"))
    DIGEST_MAX_JOBS: int = int(os.getenv("DIGEST_MAX_JOBS", "12"))
    DEDUP_FUZZY_THRESHOLD: float = float(os.getenv("DEDUP_FUZZY_THRESHOLD", "0.75"))
    DEDUP_WINDOW_DAYS: int = int(os.getenv("DEDUP_WINDOW_DAYS", "60"))


cfg = Config()
