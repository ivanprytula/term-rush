"""Configuration from environment variables."""

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    DATABASE_URL: PostgresDsn | None = None
    REDIS_URL: str = "redis://localhost:6379/0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    ANTHROPIC_API_KEY: str | None = None
    ENABLE_PROFANITY_CHECK: bool = True


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
