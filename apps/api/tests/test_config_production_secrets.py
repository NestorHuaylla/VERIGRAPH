import pytest

from app.core.config import Settings


def test_settings_allow_default_secrets_in_local_env() -> None:
    settings = Settings(app_env="local")
    assert settings.jwt_secret == "change-me-local-jwt-secret"


def test_settings_reject_default_jwt_secret_in_production() -> None:
    with pytest.raises(ValueError, match="jwt_secret"):
        Settings(app_env="production")


def test_settings_allow_production_with_all_secrets_overridden() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="a-real-random-secret",
        neo4j_password="a-real-neo4j-password",
        s3_secret_key="a-real-s3-secret",
    )
    assert settings.app_env == "production"
