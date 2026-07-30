from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/postgres"

    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_dir: str = str(Path.cwd() / "sessions")

    host: str = "0.0.0.0"
    port: int = 8001

    job_ttl_hours: int = 72
    ttl_cleanup_interval_minutes: int = 60

    resend_api_key: str = ""
    resend_from_email: str = "onboarding@resend.dev"
    admin_alert_email: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
