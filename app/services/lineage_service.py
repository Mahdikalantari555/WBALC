"""Scientific lineage: content identity, canonical manifests, artifact integrity.

Phase 3. Three rules drive everything here:

1. **Hashes describe bytes that still exist.** A hash is computed at upload time
   from the bytes actually written, or it is not recorded at all — legacy rows
   read "unavailable", never a fabricated identity.
2. **Manifests are canonical.** Serialisation is JSON with sorted keys, compact
   separators and no floats-with-quirks, so the same logical manifest always
   hashes the same. Machine-local absolute paths and anything secret-like are
   excluded.
3. **A failed check fails the request.** A missing or modified artifact is an
   integrity error, not a warning, and the recorded row is left untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

# Bumped when the manifest's own shape changes: a hash is only comparable
# between manifests that were built the same way.
MANIFEST_VERSION = "run-manifest-v1"

# Never part of a manifest, even if a caller hands us a dict containing them.
_SECRET_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "cookie",
)

HASH_CHUNK = 1024 * 1024


class IntegrityError(RuntimeError):
    """An artifact no longer matches the checksum recorded when it was written."""


def sha256_file(path: str | Path) -> str:
    """Streaming SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: str | Path) -> dict | None:
    """Content identity of a physical file, or None when it is not there."""
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None
    return {
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
    }


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def scrub(value: Any, *, storage_dir: str | Path | None = None) -> Any:
    """Recursively drop secret-looking keys and machine-local paths.

    Absolute paths are replaced by their basename: a manifest must describe the
    *content*, and a sandbox path says nothing reproducible about it.
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _is_secret_key(str(key)):
                continue
            cleaned[str(key)] = scrub(item, storage_dir=storage_dir)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [scrub(item, storage_dir=storage_dir) for item in value]
    if isinstance(value, str) and value.startswith(os.sep):
        return Path(value).name
    if isinstance(value, Path):
        return value.name
    return value


def canonical_bytes(payload: Any) -> bytes:
    """Canonical JSON: sorted keys, compact separators, UTF-8, no NaN."""
    serialised = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return serialised.encode("utf-8")


def digest(payload: Any) -> str:
    """SHA-256 of the canonical serialisation."""
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def label_snapshot(labels: list) -> dict:
    """Exactly which label *versions* trained a model.

    Version identity (not just sample ids) is what makes a corrected label a
    different training input: version 2 of a sample replaces version 1.
    """
    effective: list[dict] = []
    for label in labels:
        effective.append(
            {
                "label_id": label.id,
                "sample_id": label.sample_id,
                "version": label.version,
                "iteration": label.iteration,
                "class_name": label.class_name,
                "dataset_id": label.dataset_id,
                "query_batch_id": getattr(label, "query_batch_id", None),
                "query_item_id": getattr(label, "query_item_id", None),
            }
        )
    effective.sort(key=lambda entry: (entry["sample_id"], entry["version"]))
    return {
        "count": len(effective),
        "versions": effective,
        "hash": digest([{k: e[k] for k in ("sample_id", "version", "class_name", "dataset_id")} for e in effective]),
    }


def dataset_manifest(dataset, *, storage_dir: str | Path | None = None) -> dict:
    """Immutable description of one training input.

    `content_sha256` is the only field that proves *which bytes* were used; when
    it is absent the entry (and the run) is reported as incomplete.
    """
    band_schema = dataset.band_schema or {}
    return {
        "dataset_id": dataset.id,
        "filename": dataset.filename,
        "content_sha256": getattr(dataset, "content_sha256", None),
        "size_bytes": getattr(dataset, "size_bytes", None),
        "grid": {
            "width": dataset.width,
            "height": dataset.height,
            "bands": dataset.bands,
            "crs": dataset.crs,
            "transform": dataset.transform,
        },
        "band_schema": {
            "declared": bool(band_schema.get("declared")),
            "sensor": band_schema.get("sensor"),
            "digest": band_schema.get("digest"),
            "bands": [
                band.get("name") if isinstance(band, dict) else band
                for band in (band_schema.get("bands") or [])
            ],
        },
    }


def build_run_manifest(
    *,
    project,
    run_config: dict,
    datasets: list,
    labels: list,
    taxonomy: dict,
    band_schema: dict,
    storage_dir: str | Path | None = None,
) -> dict:
    """The reproducibility manifest stored on a training run.

    Everything that decides the resulting numbers is in here, and nothing that
    does not: no paths, no credentials, no timestamps that would make an
    otherwise identical setup hash differently.
    """
    snapshot = label_snapshot(labels)
    inputs = [dataset_manifest(ds) for ds in datasets]
    inputs.sort(key=lambda entry: entry["dataset_id"])
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "project_id": project.id,
        "classes": list(project.classes),
        "taxonomy": {
            "version": (taxonomy or {}).get("version"),
            "source": (taxonomy or {}).get("source"),
            "classes": (taxonomy or {}).get("classes"),
            "binary_interpretation": (taxonomy or {}).get("binary_interpretation"),
        },
        "inputs": inputs,
        "labels": {
            "count": snapshot["count"],
            "hash": snapshot["hash"],
            "versions": snapshot["versions"],
        },
        "feature_schema": {
            "band_schema": band_schema or {},
        },
        "config": run_config,
        "environment": environment_identity(),
    }
    manifest = scrub(manifest, storage_dir=storage_dir)
    manifest["hash"] = digest({k: v for k, v in manifest.items() if k != "hash"})
    # A run is only "complete" when every input and the code identity exist.
    missing: list[str] = []
    for entry in inputs:
        if not entry.get("content_sha256"):
            missing.append(f"dataset {entry['dataset_id']}: content hash")
    if not manifest["environment"].get("revision"):
        missing.append("code revision")
    manifest["complete"] = not missing
    manifest["missing"] = missing
    return manifest


def environment_identity() -> dict:
    """Best-effort, honest environment identity.

    When the revision cannot be determined (no git metadata, no baked env var) it
    stays `None` and the run is reported incomplete rather than guessed.
    """
    revision = os.environ.get("WBALC_CODE_REVISION")
    if not revision:
        head = Path(__file__).resolve().parents[2] / ".git" / "HEAD"
        try:
            raw = head.read_text().strip()
            if raw.startswith("ref:"):
                ref = head.parent / raw.split(" ", 1)[1].strip()
                revision = ref.read_text().strip()
            else:
                revision = raw
        except OSError:
            revision = None
    return {
        "revision": revision or None,
        "revision_source": "env" if os.environ.get("WBALC_CODE_REVISION") else ("git" if revision else None),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "packages": package_identity(),
    }


def package_identity() -> dict:
    """Versions of the libraries that decide the numbers.

    Deliberately a short, stable list: it is part of the manifest hash, so it
    must not include anything that changes without affecting results.
    """
    from importlib import metadata

    versions: dict[str, str | None] = {}
    for name in ("numpy", "scikit-learn", "scipy", "rasterio", "lightgbm", "joblib"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def verify_artifact(path: str | Path, expected: str | None) -> dict:
    """Check a stored artifact against its recorded checksum.

    Returns the observed identity. Raises IntegrityError when the file is gone or
    has changed — a download must never quietly serve altered bytes — and states
    plainly when no checksum was ever recorded (legacy artifact), which is not the
    same thing as passing.
    """
    target = Path(path)
    if not target.exists():
        raise IntegrityError(f"Artifact '{target.name}' is missing from storage")
    actual = sha256_file(target)
    if expected is None:
        return {
            "verified": False,
            "reason": "no checksum was recorded for this artifact (legacy)",
            "sha256": actual,
        }
    if actual != expected:
        raise IntegrityError(
            f"Artifact '{target.name}' does not match its recorded checksum "
            f"(recorded {expected[:12]}…, found {actual[:12]}…); refusing to serve it"
        )
    return {"verified": True, "sha256": actual}
