from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_password"  # noqa: S105
    POSTGRES_DB: str = "ai_email_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5434

    CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:3000"]

    @computed_field
    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        # SQLAlchemy async DSN format using asyncpg driver
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6381

    @computed_field
    @property
    def REDIS_URL(self) -> str:  # noqa: N802
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # API Keys
    GMAIL_CLIENT_ID: str | None = None
    GMAIL_CLIENT_SECRET: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    PUBSUB_PROJECT_ID: str | None = None

    # Pub/Sub OIDC audience — set to your webhook URL in production
    # e.g. "https://your-domain.com/api/v1/webhook/gmail"
    # When None, OIDC verification is skipped (dev mode)
    PUBSUB_AUDIENCE: str | None = None

    # App
    LOG_LEVEL: str = "INFO"

    # Pydantic config: read from .env, ignore unknown fields
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
