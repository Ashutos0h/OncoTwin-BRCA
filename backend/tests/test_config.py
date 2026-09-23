import pytest

from backend.app.config import DEFAULT_CORS_ORIGINS, Settings


def test_development_defaults(monkeypatch):
    for name in (
        "APP_ENV",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "AUTH_ENABLED",
        "READER_API_KEY",
        "WRITER_API_KEY",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.app_env == "development"
    assert settings.database_url is None
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.auth_enabled is False


def test_production_requires_database_and_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings.from_env()


def test_enabled_auth_requires_two_distinct_keys(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("READER_API_KEY", raising=False)
    monkeypatch.delenv("WRITER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="required"):
        Settings.from_env()

    monkeypatch.setenv("READER_API_KEY", "same")
    monkeypatch.setenv("WRITER_API_KEY", "same")
    with pytest.raises(ValueError, match="different"):
        Settings.from_env()


def test_valid_production_configuration(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://oncotwin:secret@db:5432/oncotwin"
    )
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("READER_API_KEY", "r" * 32)
    monkeypatch.setenv("WRITER_API_KEY", "w" * 32)
    settings = Settings.from_env()
    assert settings.app_env == "production"
    assert settings.auth_enabled is True


def test_production_rejects_sqlite_and_short_keys(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("READER_API_KEY", "r" * 32)
    monkeypatch.setenv("WRITER_API_KEY", "w" * 32)
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings.from_env()

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/name")
    monkeypatch.setenv("READER_API_KEY", "short")
    with pytest.raises(ValueError, match="at least 32"):
        Settings.from_env()
