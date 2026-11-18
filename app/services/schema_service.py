"""Declared input feature schema for a raster band stack.

Band *count* is not semantic identity: a four-band stack can be Sentinel-2
blue/green/red/nir in one order and a completely different sensor's four bands in
another. This module builds a stable, serialisable description of a raster's
ordered bands so training and inference can compare *meaning*, and can say
"unknown" instead of guessing.

Nothing here infers a band's meaning from a filename or from a sensor default.
A schema is only *declared* when the file itself carries names/descriptions, or
when a caller explicitly provides band names for the upload.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "band-schema-v1"
UNNAMED = "unnamed"


def normalise_band_names(names: list[str | None] | None) -> list[str] | None:
    """Trim names and treat blanks as absent, so `[]` never claims to be a schema."""
    if not names:
        return None
    cleaned = [name.strip() if isinstance(name, str) else "" for name in names]
    if not any(cleaned):
        return None
    return [name or UNNAMED for name in cleaned]


def build_band_schema(
    *,
    band_count: int,
    band_names: list[str | None] | None = None,
    sensor: str | None = None,
    source: str = "raster-metadata",
) -> dict[str, Any]:
    """Describe ordered bands.

    `declared` is True only when every band has a name: a partially named stack
    cannot prove positional equivalence, and pretending otherwise is exactly the
    failure mode this contract exists to prevent.
    """
    names = normalise_band_names(band_names)
    fully_named = bool(names) and len(names) == band_count and UNNAMED not in names
    # An all-unnamed stack carries no identity beyond its width.
    schema = {
        "version": SCHEMA_VERSION,
        "band_count": int(band_count),
        "band_names": names if fully_named else None,
        "sensor": sensor or None,
        "declared": fully_named,
        "source": source,
    }
    schema["digest"] = schema_digest(schema)
    return schema


def schema_digest(schema: dict[str, Any] | None) -> str | None:
    """Canonical digest over the *ordered band identity*.

    The sensor label is deliberately not part of the digest: it is useful
    corroboration when both sides declare it (see `compare_schemas`), but a
    raster that names its bands and omits the sensor still carries a provable
    band identity. The source label is metadata about where the names came from.
    """
    if not schema:
        return None
    payload = {
        "version": schema.get("version"),
        "band_count": schema.get("band_count"),
        "band_names": schema.get("band_names"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


class SchemaConflict(ValueError):
    """Two inputs cannot be proven to describe the same ordered bands."""


def compare_schemas(
    expected: dict[str, Any] | None,
    actual: dict[str, Any] | None,
    *,
    expected_band_count: int | None = None,
    actual_band_count: int | None = None,
) -> tuple[bool, str]:
    """Return (verified, reason).

    `verified` means "these two inputs provably carry the same ordered bands".
    It is False whenever either side is undeclared, even when the widths match:
    a band-count match is not evidence of meaning.
    """
    expected_count = expected_band_count if expected_band_count is not None else (expected or {}).get("band_count")
    actual_count = actual_band_count if actual_band_count is not None else (actual or {}).get("band_count")
    if expected_count is not None and actual_count is not None and expected_count != actual_count:
        return False, f"band count differs ({expected_count} vs {actual_count})"
    if not expected:
        return False, "the model records no band schema (checkpoint predates schema recording)"
    if not expected.get("declared"):
        return False, "the model's band schema is not declared (bands were unnamed at training time)"
    if not actual:
        return False, "the selected raster records no band schema"
    if not actual.get("declared"):
        return False, "the selected raster's bands are unnamed"
    if expected.get("band_names") != actual.get("band_names"):
        return False, (
            "ordered band names differ "
            f"({', '.join(expected.get('band_names') or [])} vs {', '.join(actual.get('band_names') or [])})"
        )
    # Sensor is checked only when both sides declare one; a missing sensor label
    # does not weaken an otherwise identical ordered band list.
    if expected.get("sensor") and actual.get("sensor") and expected["sensor"] != actual["sensor"]:
        return False, f"sensor differs ({expected['sensor']} vs {actual['sensor']})"
    if expected.get("digest") != schema_digest(actual):
        return False, "band schema digests differ"
    return True, "ordered band schema matches"
