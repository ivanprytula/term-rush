"""Configuration from environment variables."""

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    """Pipeline settings from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    ANTHROPIC_API_KEY: str | None = None
    CONTENT_SERVICE_URL: str = "http://localhost:8001"
    DOCUMENT_INTAKE_DIR: str = "intake/documents"


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
