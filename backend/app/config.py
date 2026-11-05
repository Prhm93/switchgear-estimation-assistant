"""Application settings, read from environment variables.

Every deployment-specific value lives here so the same image runs on a
laptop, in CI and on a server. Unset values fall back to safe defaults: with
no DATABASE_URL the app still starts and reports the database as
"not configured".
"""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Typed app configuration. Field names map to upper-case env variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", populate_by_name=True)

    app_name: str = "Switchgear Estimation Assistant"
    environment: Environment = Field(default="development", alias="APP_ENV")
    database_url: str | None = Field(
        default=None,
        description="SQLAlchemy URL, e.g. postgresql+pg8000://user:pass@db:5432/sea",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        """Treat DATABASE_URL="" as not configured rather than as a bad URL."""
        if isinstance(value, str) and not value.strip():
            return None
        return value
