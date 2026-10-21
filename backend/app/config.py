"""Environment-backed application configuration with production safeguards."""

from dataclasses import dataclass
import os


DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    database_url: str | None = None
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    auth_enabled: bool = False
    reader_api_key: str | None = None
    writer_api_key: str | None = None
    log_level: str = "INFO"
    ml_inference_mode: str = "mock"

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            database_url=os.getenv("DATABASE_URL") or None,
            cors_origins=tuple(
                value.strip()
                for value in os.getenv(
                    "CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)
                ).split(",")
                if value.strip()
            ),
            auth_enabled=_boolean("AUTH_ENABLED", False),
            reader_api_key=os.getenv("READER_API_KEY") or None,
            writer_api_key=os.getenv("WRITER_API_KEY") or None,
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            ml_inference_mode=(
                os.getenv("ML_INFERENCE_MODE")
                or os.getenv("ONCOTWIN_ML_INFERENCE_MODE")
                or "mock"
            ).strip().lower(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production.")
        if self.ml_inference_mode not in {"mock", "trained"}:
            raise ValueError("ML_INFERENCE_MODE must be 'mock' or 'trained'.")
        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin.")
        if self.auth_enabled and (not self.reader_api_key or not self.writer_api_key):
            raise ValueError(
                "READER_API_KEY and WRITER_API_KEY are required when AUTH_ENABLED=true."
            )
        if self.reader_api_key and self.writer_api_key == self.reader_api_key:
            raise ValueError("Reader and writer API keys must be different.")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        if self.app_env == "production":
            if not self.database_url:
                raise ValueError("DATABASE_URL is required in production.")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production DATABASE_URL must use PostgreSQL.")
            if not self.auth_enabled:
                raise ValueError("AUTH_ENABLED must be true in production.")
            if len(self.reader_api_key or "") < 32 or len(self.writer_api_key or "") < 32:
                raise ValueError("Production API keys must be at least 32 characters.")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production.")
