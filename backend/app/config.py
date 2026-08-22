"""Environment-derived settings.

Two different things are called "config" in this app and it is worth keeping
them apart:

* **Settings** (this module) come from the environment and describe the
  machine — where storage lives, which database, which salt. They do not
  change while the app runs.
* **App configuration** (``app.services.config_store``) is the field map,
  carrier details, and signature placement. The reviewer edits those through
  the settings screen, so they live on disk as JSON and change at runtime.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Network ---
    # 127.0.0.1 is a compliance requirement, not a default. See CLAUDE.md.
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    #: Only turn on behind HTTPS. On a private network the desk is served
    #: over plain HTTP and a secure-only cookie would never be sent.
    session_cookie_secure: bool = False

    # --- Storage ---
    storage_root: Path = Path("storage")

    # --- Database ---
    database_url: str = "sqlite:///./contract_desk.db"

    # --- Secrets ---
    ssn_salt: str = "change-me-before-first-real-contract"

    # --- Limits ---
    max_upload_mb: int = 50

    @field_validator("storage_root")
    @classmethod
    def _absolutise(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_ROOT / value)

    @property
    def is_loopback(self) -> bool:
        """Is the app answering only to the machine it runs on?"""

        return self.host in {"127.0.0.1", "localhost", "::1"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def executed_dir(self) -> Path:
        return self.storage_root / "executed"

    @property
    def signatures_dir(self) -> Path:
        return self.storage_root / "signatures"

    @property
    def config_dir(self) -> Path:
        return self.storage_root / "config"

    @property
    def templates_dir(self) -> Path:
        """Source PDFs for placement templates: completed, signed contracts."""

        return self.storage_root / "templates"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for directory in (
            self.uploads_dir,
            self.executed_dir,
            self.signatures_dir,
            self.config_dir,
            self.templates_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
