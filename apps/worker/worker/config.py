from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    redis_url: str = "redis://redis:6379/0"
    api_base_url: str = "http://api:8000"
    worker_api_token: str = ""

    virustotal_api_key: str = ""
    google_safe_browsing_api_key: str = ""
    phishtank_api_key: str = ""
    urlhaus_auth_key: str = ""
    urlscan_api_key: str = ""

    notification_webhook_url: str = ""
    slack_webhook_url: str = ""
    alert_email_to: str = ""
    alert_email_from: str = "alerts@verigraph.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()


settings = get_settings()
