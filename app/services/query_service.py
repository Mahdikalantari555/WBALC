"""Sampling-strategy helpers shared by every query path (Phase 2).

Two things live here because both must be identical for all strategies:

- the **candidate pool** is described once (`describe_pool`), so a batch can say
  which pool it sampled from and two batches can be proved comparable;
- the **seeded random baseline** (`select_random`) draws without replacement from
  exactly that pool, which is what makes an active-learning comparison honest.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

# Bumped when a strategy's selection rule changes, so an old batch is never
# silently reinterpreted as if it had been produced by the new rule.
STRATEGY_VERSION = "query-v1"

# Pixel pools are subsampled to stay tractable: ~50k candidates keeps
# kcenter responsive on large scenes without changing the ranking
# semantics (every candidate is still one real, valid pixel).
PIXEL_POOL_TARGET = 50_000
PIXEL_POOL_MAX_STRIDE = 8


def pixel_query_stride(height: int, width: int, requested: int | None) -> int:
    """Stride of a pixel query pool: explicit when requested, else bounded."""
    if requested is not None:
        return requested
    natural = math.ceil(math.sqrt((height * width) / PIXEL_POOL_TARGET))
    return max(1, min(natural, PIXEL_POOL_MAX_STRIDE))


class QuerySelectionError(ValueError):
    """A request the engine refuses rather than silently degrading."""


def pool_hash(sample_ids: list[str]) -> str:
    """Stable digest of the *ordered* eligible candidate set.

    Order matters: it is the order the strategy indexes into, so the same set in
    a different order is a different pool for reproducibility purposes.
    """
    digest = hashlib.sha256()
    for sid in sample_ids:
        digest.update(sid.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def describe_pool(
    sample_ids: list[str],
    *,
    patch_size: int,
    stride: int,
    grid_rows: int,
    grid_cols: int,
    exclude_labeled: bool,
    n_labeled_patches: int,
    n_grid_cells: int,
) -> dict:
    """Everything needed to re-derive the pool without re-running the query."""
    return {
        "size": len(sample_ids),
        "hash": pool_hash(sample_ids),
        "patch_size": patch_size,
        "stride": stride,
        "grid": {"rows": grid_rows, "cols": grid_cols},
        "grid_cells": n_grid_cells,
        "n_labeled_patches": n_labeled_patches,
        "exclude_labeled": exclude_labeled,
        # Patches with no valid source pixel are never eligible; recorded so the
        # exclusion is auditable rather than implied.
        "eligibility": "valid-source-pixels" + (" and unlabeled" if exclude_labeled else ""),
    }


def resolve_seed(strategy: str, requested: int | None, default: int) -> int | None:
    """Random strategies always get a recorded seed; deterministic ones get None.

    A strategy that makes no random draw must not claim a seed, otherwise the
    stored record would suggest a reproducibility guarantee it never had.
    """
    if strategy != "random":
        return None
    return default if requested is None else requested


def select_random(
    sample_ids: list[str], batch_size: int, seed: int
) -> list[int]:
    """Draw `batch_size` pool indices without replacement, seeded and repeatable.

    Positions are drawn by permutation of the pool indices, so the same seed and
    the same ordered pool always yields the same items in the same order.
    """
    n = len(sample_ids)
    if n == 0 or batch_size <= 0:
        return []
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    return [int(i) for i in order[: min(batch_size, n)]]


def pool_manifest(entries: list[dict]) -> str:
    """Serialise the pool description for storage in a JSON column."""
    return json.dumps(entries, sort_keys=True)
