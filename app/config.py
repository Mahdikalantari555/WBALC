"""Application configuration via environment variables / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage root for uploads, model checkpoints, exports and (by default) SQLite.
    storage_dir: Path = Path("storage")

    # SQLAlchemy async URL. Defaults to SQLite under STORAGE_DIR.
    # Postgres example: postgresql+asyncpg://user:pass@host:5432/rsal
    database_url: str | None = None

    # Patch grid defaults (design.md open question resolved: 32px windows, non-overlap).
    patch_size: int = 32
    stride: int | None = None  # defaults to patch_size

    # Training defaults
    test_size: float = 0.25
    random_state: int = 42

    # Guard rail for the MVP in-memory raster processing (elements = H*W*bands).
    max_raster_elements: int = 250_000_000

    # Upload limit (bytes). 512 MiB.
    max_upload_bytes: int = 512 * 1024 * 1024

    def resolved_database_url(self) -> str:
        if self.database_url:
            url = self.database_url
            # Accept plain postgres URLs and map them to the async driver.
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        db_path = (self.storage_dir / "rsal.db").resolve()
        return f"sqlite+aiosqlite:///{db_path}"

    def resolved_stride(self) -> int:
        return self.stride or self.patch_size


settings = Settings()
