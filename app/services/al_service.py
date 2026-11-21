"""Active learning query strategies over patch embeddings / probabilities.

- uncertainty: least confidence, margin, entropy (higher score = more informative)
- diversity: greedy k-center core-set over embeddings (farthest-first traversal)
- hybrid: pre-select a top-uncertainty pool, then k-center within the pool
"""

from __future__ import annotations

import math

import numpy as np

UNCERTAINTY_METHODS = ("least_confidence", "margin", "entropy")


def uncertainty_scores(probs: np.ndarray, method: str = "least_confidence") -> np.ndarray:
    """probs: (n, k) class probabilities -> (n,) scores in [0, 1], higher = more uncertain."""
    probs = np.clip(np.asarray(probs, dtype=np.float64), 1e-12, 1.0)
    probs = probs / probs.sum(axis=1, keepdims=True)
    if method == "least_confidence":
        return 1.0 - probs.max(axis=1)
    if method == "margin":
        if probs.shape[1] < 2:
            return np.zeros(len(probs))
        top2 = np.partition(probs, -2, axis=1)[:, -2:]
        return 1.0 - (top2[:, 1] - top2[:, 0])
    if method == "entropy":
        k = probs.shape[1]
        if k < 2:
            return np.zeros(len(probs))
        ent = -(probs * np.log(probs)).sum(axis=1)
        return ent / np.log(k)
    raise ValueError(f"Unknown uncertainty method '{method}'")


def _standardize(embeddings: np.ndarray) -> np.ndarray:
    mu = embeddings.mean(axis=0)
    sigma = embeddings.std(axis=0)
    sigma[sigma < 1e-9] = 1.0
    return (embeddings - mu) / sigma


def kcenter_greedy(
    embeddings: np.ndarray,
    batch_size: int,
    seed_embeddings: np.ndarray | None = None,
) -> list[int]:
    """Greedy core-set selection. Returns indices in selection order.

    When seed embeddings (already-labeled points) are given, coverage starts
    from them; otherwise the first pick is the point farthest from the mean.
    """
    n = len(embeddings)
    if n == 0 or batch_size <= 0:
        return []
    batch_size = min(batch_size, n)
    X = _standardize(embeddings)

    if seed_embeddings is not None and len(seed_embeddings) > 0:
        # standardize seeds with the pool statistics for comparability
        mu = embeddings.mean(axis=0)
        sigma = embeddings.std(axis=0)
        sigma[sigma < 1e-9] = 1.0
        seeds = (np.asarray(seed_embeddings, dtype=np.float64) - mu) / sigma
        min_dist = np.min(((X[:, None, :] - seeds[None, :, :]) ** 2).sum(axis=2), axis=1)
        selected: list[int] = []
    else:
        center = X.mean(axis=0)
        dists = ((X - center) ** 2).sum(axis=1)
        first = int(np.argmax(dists))
        selected = [first]
        min_dist = ((X - X[first]) ** 2).sum(axis=1)
        min_dist[first] = -1.0

    while len(selected) < batch_size:
        idx = int(np.argmax(min_dist))
        if min_dist[idx] < 0:  # everything already selected
            break
        selected.append(idx)
        min_dist = np.minimum(min_dist, ((X - X[idx]) ** 2).sum(axis=1))
        for s in selected:
            min_dist[s] = -1.0
    return selected


def select_uncertainty(scores: np.ndarray, batch_size: int) -> list[int]:
    """Indices of the batch_size highest scores, descending (stable)."""
    n = len(scores)
    order = np.argsort(-np.asarray(scores), kind="stable")
    return [int(i) for i in order[: min(batch_size, n)]]


def select_hybrid(
    scores: np.ndarray,
    embeddings: np.ndarray,
    batch_size: int,
    pool_multiplier: int = 5,
    seed_embeddings: np.ndarray | None = None,
) -> list[int]:
    """Uncertainty pre-filter then core-set diversification within the pool."""
    n = len(scores)
    if n == 0 or batch_size <= 0:
        return []
    pool_size = min(n, max(batch_size, batch_size * pool_multiplier))
    pool = select_uncertainty(scores, pool_size)
    picked = kcenter_greedy(embeddings[pool], batch_size, seed_embeddings)
    return [pool[i] for i in picked]


