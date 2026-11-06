"""Application settings, read from environment variables.

Every deployment-specific value lives here so the same image runs on a
laptop, in CI and on a server. Unset values fall back to safe defaults: with
no DATABASE_URL the app still starts and reports the database as
"not configured".
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import REPO_ROOT

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

    # Uploads: originals are stored unchanged under generated keys in this folder.
    storage_dir: Path = Field(default=REPO_ROOT / "storage", description="STORAGE_DIR")
    max_upload_mb: int = Field(default=25, ge=1, description="MAX_UPLOAD_MB: largest accepted file")
    max_pdf_pages: int = Field(default=60, ge=1, description="MAX_PDF_PAGES: longest accepted PDF")
    # Rules mode inputs.
    catalogue_csv: Path = Field(default=REPO_ROOT / "data" / "catalogue" / "catalogue.csv")
    estimate_rules: Path = Field(default=REPO_ROOT / "config" / "estimate.toml")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1_000_000

    @field_validator("database_url", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        """Treat DATABASE_URL="" as not configured rather than as a bad URL."""
        if isinstance(value, str) and not value.strip():
            return None
        return value
