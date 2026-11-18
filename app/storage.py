"""Filesystem layout helpers. Everything lives under STORAGE_DIR.

storage/
  rsal.db                          # SQLite (default)
  uploads/project_<id>/<file>      # original GeoTIFFs
  models/project_<id>/<file>       # joblib checkpoints
  exports/project_<id>/<file>      # GeoTIFF results
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .config import Settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = _SAFE.sub("_", name).strip("._") or "file"
    return name[:120]


def unique_name(original: str) -> str:
    return f"{uuid.uuid4().hex[:12]}_{safe_filename(original)}"


def ensure_dirs(settings: Settings) -> None:
    for sub in ("uploads", "models", "exports"):
        (settings.storage_dir / sub).mkdir(parents=True, exist_ok=True)


def project_dir(settings: Settings, kind: str, project_id: int) -> Path:
    path = settings.storage_dir / kind / f"project_{project_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path
