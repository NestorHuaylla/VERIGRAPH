from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_NETWORK_CORS_ORIGIN_REGEX = (
    r"https?://("
    r"localhost|127\.0\.0\.1|\[::1\]|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "VERIGRAPH"
    app_env: str = "local"
    app_debug: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str | None = LOCAL_NETWORK_CORS_ORIGIN_REGEX

    database_url: str = "postgresql+asyncpg://verigraph:verigraph@postgres:5432/verigraph"
    redis_url: str = "redis://redis:6379/0"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "verigraph-local"

    s3_endpoint: str = "http://minio:9000"
    s3_bucket_evidence: str = "verigraph-evidence"
    s3_access_key: str = "verigraph"
    s3_secret_key: str = "verigraph-local"
    s3_region: str = "us-east-1"
    evidence_storage_backend: str = "local"

    jwt_secret: str = "change-me-local-jwt-secret"
    jwt_issuer: str = "verigraph-local"
    access_token_expire_minutes: int = 60
    worker_api_token: str = ""
    keycloak_issuer: str = ""
    keycloak_client_id: str = "verigraph-web"
    keycloak_auto_provision_users: bool = True

    notification_webhook_url: str = ""
    slack_webhook_url: str = ""
    alert_email_to: str = ""
    alert_email_from: str = "alerts@verigraph.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    rate_limit_per_minute: int = 60
    max_evidence_upload_mb: int = 20
    local_evidence_storage_path: str = "storage/evidence"

    # IPs/redes de proxies confiables (nginx, load balancer, etc.) autorizadas
    # a enviar X-Forwarded-For / X-Real-IP. Si la conexion TCP no viene de una
    # de estas redes, esos headers se ignoran y se usa la IP directa del
    # socket, para evitar que un cliente falsifique su propia IP.
    trusted_proxy_networks: list[str] = Field(
        default_factory=lambda: ["127.0.0.1/32", "::1/128"]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
