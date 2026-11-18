"""Water-body taxonomy, label crosswalk and derived binary interpretation.

Phase 1 makes the water-body classification contract explicit instead of implied
by project configuration:

- a **versioned taxonomy** with stable class IDs in a fixed order;
- a **label crosswalk** from human-entered label text to those IDs, so a term like
  ``reed`` is only ever an *explicit project decision*, never a silent synonym;
- a **derived binary product** with a documented mapping that never overwrites the
  three-class source product.

Nothing here guesses domain meaning. If a project has not configured an alias, the
alias does not exist; if a mapping needs a class the model never learned, the
binary product is reported unavailable instead of being fabricated.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# ---------------------------------------------------------------- taxonomy
TAXONOMY_VERSION = "wbalc-water-taxonomy-v1"
INTERNAL_CLASSES: list[str] = ["open_water", "emergent_vegetation", "land"]

# Human-readable labels are UI copy, not classifier identity: exports and
# checkpoints always use the stable IDs above.
CLASS_DISPLAY_NAMES: dict[str, str] = {
    "open_water": "Open water",
    "emergent_vegetation": "Emergent vegetation",
    "land": "Land",
}


class TaxonomyError(ValueError):
    """The taxonomy or crosswalk configuration is not usable."""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def normalise_aliases(aliases: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """Normalise alias keys to slugs and drop blanks/duplicates, keeping order.

    The canonical class ID is always its own alias, so a label literally named
    ``open_water`` resolves without extra configuration.
    """
    out: dict[str, list[str]] = {}
    for canonical, terms in (aliases or {}).items():
        key = _slug(canonical)
        if key not in INTERNAL_CLASSES:
            raise TaxonomyError(
                f"unknown canonical class '{canonical}'; the water taxonomy is "
                f"{', '.join(INTERNAL_CLASSES)}"
            )
        cleaned: list[str] = []
        for term in [key, *(terms or [])]:
            if not isinstance(term, str):
                raise TaxonomyError(f"alias for '{key}' must be a string, got {type(term).__name__}")
            slug = _slug(term)
            if slug and slug not in cleaned:
                cleaned.append(slug)
        out[key] = cleaned
    return out


def build_taxonomy(
    *,
    version: str = TAXONOMY_VERSION,
    aliases: dict[str, list[str]] | None = None,
    binary_interpretation: str = "water_vs_non_water",
    source: str = "default",
) -> dict[str, Any]:
    """Return the serialisable taxonomy snapshot stored with a project.

    ``source`` records whether this came from the WBALC defaults or from an
    explicit project configuration, so a generic legacy project is
    distinguishable from a project that opted into the water taxonomy.
    """
    if binary_interpretation not in BINARY_MAPPINGS:
        raise TaxonomyError(
            f"unknown binary interpretation '{binary_interpretation}'; "
            f"use one of {', '.join(BINARY_MAPPINGS)}"
        )
    normalised = normalise_aliases(aliases)
    for canonical in INTERNAL_CLASSES:
        # Every canonical class is its own alias, so an unconfigured project still
        # resolves labels that use the class IDs directly.
        normalised.setdefault(canonical, [canonical])
    crosswalk: dict[str, str] = {}
    for canonical, terms in normalised.items():
        for term in terms:
            existing = crosswalk.get(term)
            if existing is not None and existing != canonical:
                raise TaxonomyError(
                    f"alias '{term}' is ambiguous: mapped to both '{existing}' and "
                    f"'{canonical}'. Each alias must resolve to exactly one class."
                )
            crosswalk[term] = canonical
    return {
        "version": version,
        "classes": list(INTERNAL_CLASSES),
        "display_names": dict(CLASS_DISPLAY_NAMES),
        "aliases": normalised,
        "crosswalk": crosswalk,
        "binary_interpretation": binary_interpretation,
        "source": source,
    }


def resolve_label_class(name: str, taxonomy: dict[str, Any] | None) -> str | None:
    """Map submitted label text to a canonical class ID, or ``None``.

    A ``None`` means "no unique configured mapping" — the caller must reject the
    label with an actionable message rather than coercing it.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    term = _slug(name)
    crosswalk = (taxonomy or {}).get("crosswalk")
    if crosswalk:
        return crosswalk.get(term)
    # Legacy project without a taxonomy: exact ID match only, slugged. A generic
    # project's own class list is the caller's authority; this helper only knows
    # the WBALC classes.
    return term if term in INTERNAL_CLASSES else None


def alias_suggestions(name: str, taxonomy: dict[str, Any] | None) -> list[str]:
    """Classes whose configured aliases look similar, for a helpful error."""
    term = _slug(name)
    out: list[str] = []
    aliases = (taxonomy or {}).get("aliases") or {}
    for canonical, terms in aliases.items():
        if any(term and (term in t or t in term) for t in terms):
            out.append(canonical)
    return out


# ------------------------------------------------- derived binary product
# The three-class product is the source of truth; these mappings only derive a
# second, separately identified product from it.
BINARY_MAPPINGS: dict[str, dict[str, Any]] = {
    "water_vs_non_water": {
        "version": "binary-water-v1",
        "water": ["open_water", "emergent_vegetation"],
        "other": ["land"],
    },
    "open_water_vs_other": {
        "version": "binary-water-v1",
        "water": ["open_water"],
        "other": ["emergent_vegetation", "land"],
    },
}

BINARY_CLASSES = ["water", "non_water"]
# Stable binary codes written into derived rasters: 1 = water, 0 = other.
BINARY_CODES = {"water": 1, "non_water": 0}


def binary_plan(classes: list[str], interpretation: str) -> dict[str, Any]:
    """Describe how a binary product would be derived from ``classes``.

    Returns a dict with ``interpretation``, ``mapping`` (class → water/non_water),
    ``available`` and — when unavailable — a ``reason`` that names the classes the
    model never learned. No probabilities are synthesised for absent classes.
    """
    if interpretation not in BINARY_MAPPINGS:
        raise TaxonomyError(
            f"unknown binary interpretation '{interpretation}'; "
            f"use one of {', '.join(BINARY_MAPPINGS)}"
        )
    mapping = BINARY_MAPPINGS[interpretation]
    missing = [c for c in mapping["water"] + mapping["other"] if c not in classes]
    plan: dict[str, Any] = {
        "interpretation": interpretation,
        "version": mapping["version"],
        "source_classes": list(classes),
        "mapping": {
            **{c: "water" for c in mapping["water"] if c in classes},
            **{c: "non_water" for c in mapping["other"] if c in classes},
        },
        "desired_mapping": {**{c: "water" for c in mapping["water"]}, **{c: "non_water" for c in mapping["other"]}},
        "available": not missing,
        "missing_classes": missing,
    }
    if missing:
        plan["reason"] = (
            "Binary interpretation "
            f"'{interpretation}' needs {', '.join(missing)}, which this model never "
            "learned (no labels for it), so the derived product would be fabricated. "
            "Label samples of that class and retrain, or use the three-class product."
        )
    return plan


def binary_hard(hard, classes: list[str], interpretation: str):
    """Derived binary class map (1 = water, 0 = other) and its validity mask."""
    import numpy as np

    plan = binary_plan(classes, interpretation)
    if not plan["available"]:
        raise TaxonomyError(plan["reason"])
    out = np.full(hard.shape, BINARY_CODES["non_water"], dtype=np.uint8)
    for index, name in enumerate(classes):
        if plan["mapping"].get(name) == "water":
            out[hard == index] = BINARY_CODES["water"]
    return out, plan


def binary_probability(prob, classes: list[str], interpretation: str):
    """Sum the source class probabilities that the mapping calls water.

    The result stays bounded in [0, 1] because it is a sum of a subset of a
    probability vector; NoData is preserved by the caller's validity mask.
    """
    import numpy as np

    plan = binary_plan(classes, interpretation)
    if not plan["available"]:
        raise TaxonomyError(plan["reason"])
    total = np.zeros(prob.shape[1:], dtype=np.float32)
    for index, name in enumerate(classes):
        if plan["mapping"].get(name) == "water":
            total += np.asarray(prob[index], dtype=np.float32)
    return np.clip(total, 0.0, 1.0), plan


def taxonomy_snapshot(
    taxonomy: dict[str, Any] | None, *, binary_interpretation: str | None = None
) -> dict[str, Any]:
    """Snapshot to record in a training run / checkpoint (immutable semantics)."""
    snapshot = dict(taxonomy or build_taxonomy())
    if binary_interpretation:
        snapshot["binary_interpretation"] = binary_interpretation
    return snapshot


def describe(classes: Iterable[str], taxonomy: dict[str, Any] | None) -> dict[str, Any]:
    """Public description of a project's class semantics for the UI/API."""
    classes = list(classes)
    aliases = (taxonomy or {}).get("aliases") or {}
    return {
        "taxonomy_version": (taxonomy or {}).get("version"),
        "source": (taxonomy or {}).get("source", "legacy"),
        "classes": classes,
        "display_names": {
            name: (taxonomy or {}).get("display_names", {}).get(name, name) for name in classes
        },
        "aliases": {name: aliases.get(name, [name]) for name in classes},
        "binary": binary_plan(classes, (taxonomy or {}).get("binary_interpretation", "water_vs_non_water")),
    }
