from functools import lru_cache

from pydantic import Field, model_validator
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
    # Antes este valor no se usaba en ningun lado (config muerta). Ahora se
    # conecta de verdad en app/main.py via FastAPI(debug=...). Default en
    # False: activarlo explicitamente solo en desarrollo si hace falta.
    app_debug: bool = False
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

    # Analisis de evidencia: OCR local (Tesseract) + fallback a AI Vision
    # (API de Anthropic) cuando Tesseract no logra un resultado confiable.
    anthropic_api_key: str = ""
    claude_vision_model: str = "claude-sonnet-5"
    ocr_language: str = "spa+eng"
    # Umbrales para decidir si el resultado de Tesseract es confiable o
    # si hace falta escalar a AI Vision.
    ocr_min_confidence: float = 60.0
    ocr_min_word_count: int = 3

    # IPs/redes de proxies confiables (nginx, load balancer, etc.) autorizadas
    # a enviar X-Forwarded-For / X-Real-IP. Si la conexion TCP no viene de una
    # de estas redes, esos headers se ignoran y se usa la IP directa del
    # socket, para evitar que un cliente falsifique su propia IP.
    trusted_proxy_networks: list[str] = Field(
        default_factory=lambda: ["127.0.0.1/32", "::1/128"]
    )

    # Cookie httpOnly usada para sesiones de navegador (login local). El
    # token tambien se devuelve en el body de /auth/login para clientes de
    # API no interactivos (scripts, Postman, apps moviles), pero el frontend
    # web NO debe leerlo ni guardarlo: debe apoyarse en esta cookie, que
    # JavaScript no puede leer, para mitigar robo de sesion via XSS.
    auth_cookie_name: str = "verigraph_access_token"
    auth_cookie_secure: bool = False  # poner en True detras de HTTPS (prod)
    auth_cookie_samesite: str = "lax"

    @model_validator(mode="after")
    def _reject_default_secrets_in_production(self) -> "Settings":
        # Si alguien olvida configurar el .env en un deploy real, la app no
        # debe arrancar igual con el JWT secret / password de Neo4j / secret
        # key de S3 que estan publicos en este repo. Solo aplica cuando
        # APP_ENV=production; en local/desarrollo los defaults son validos.
        if self.app_env != "production":
            return self

        unsafe_defaults = {
            "jwt_secret": "change-me-local-jwt-secret",
            "neo4j_password": "verigraph-local",
            "s3_secret_key": "verigraph-local",
        }
        offending = [name for name, default in unsafe_defaults.items() if getattr(self, name) == default]
        if offending:
            raise ValueError(
                "APP_ENV=production pero estas variables siguen con su valor "
                f"por defecto (inseguro): {', '.join(offending)}. "
                "Configuralas en el .env de produccion antes de arrancar."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
