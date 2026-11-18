"""Active learning query strategies over patch embeddings / probabilities.

- uncertainty: least confidence, margin, entropy (higher score = more informative)
- diversity: greedy k-center core-set over embeddings (farthest-first traversal)
- hybrid: pre-select a top-uncertainty pool, then k-center within the pool
- som: Kohonen Self-Organizing Map topological diversity / uncertainty sampling
"""

from __future__ import annotations

import math

import numpy as np

from .som_service import fit_som

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


def select_som(
    embeddings: np.ndarray,
    batch_size: int,
    seed_embeddings: np.ndarray | None = None,
    scores: np.ndarray | None = None,
    *,
    rows: int | None = None,
    cols: int | None = None,
    epochs: int = 50,
    random_state: int = 42,
    target_cell: tuple[int, int] | None = None,
    full_embeddings: np.ndarray | None = None,
    candidate_indices: np.ndarray | None = None,
    seed_indices: np.ndarray | None = None,
) -> list[int]:
    """Topological active-learning selection over a 2D Kohonen Self-Organizing Map.

    - Cold start (`scores is None`): prioritizes un-labeled SOM neurons across
      the manifold, weighting cluster density and U-Matrix boundary ridges, and
      picks each neuron's medoid first.
    - Model-guided (`scores` given): combines model uncertainty with U-Matrix
      boundary strength while distributing picks across uncovered SOM neurons.
    - Targeted cell (`target_cell=(row, col)`): selects candidates mapped to a
      specific SOM neuron so users can queue patches directly from the SOM UI.
    """
    n = len(embeddings)
    if n == 0 or batch_size <= 0:
        return []

    if full_embeddings is not None and candidate_indices is not None:
        som = fit_som(
            full_embeddings,
            rows=rows,
            cols=cols,
            epochs=epochs,
            random_state=random_state,
        )
        cand_bmus = som.bmus[candidate_indices]
        cand_dists = som.bmu_dists[candidate_indices]
        seed_bmus = (
            som.bmus[seed_indices]
            if seed_indices is not None and len(seed_indices) > 0
            else np.empty(0, dtype=np.int64)
        )
    else:
        has_seeds = seed_embeddings is not None and len(seed_embeddings) > 0
        combined = (
            np.vstack([embeddings, np.asarray(seed_embeddings, dtype=np.float64)])
            if has_seeds
            else np.asarray(embeddings, dtype=np.float64)
        )
        som = fit_som(
            combined,
            rows=rows,
            cols=cols,
            epochs=epochs,
            random_state=random_state,
        )
        cand_bmus = som.bmus[:n]
        cand_dists = som.bmu_dists[:n]
        seed_bmus = som.bmus[n:] if has_seeds else np.empty(0, dtype=np.int64)

    scores_arr = np.asarray(scores, dtype=np.float64) if scores is not None else None

    if target_cell is not None:
        tr, tc = int(target_cell[0]), int(target_cell[1])
        if not (0 <= tr < som.rows and 0 <= tc < som.cols):
            raise ValueError(
                f"som_cell ({tr}, {tc}) is out of bounds for {som.rows}x{som.cols} SOM grid"
            )
        target_m = tr * som.cols + tc
        in_cell = np.where(cand_bmus == target_m)[0]
        if len(in_cell) == 0:
            return []
        if scores_arr is not None:
            order = np.lexsort((cand_dists[in_cell], -scores_arr[in_cell]))
        else:
            order = np.argsort(cand_dists[in_cell], kind="stable")
        limit = min(batch_size, len(in_cell))
        return [int(in_cell[k]) for k in order[:limit]]

    batch_size = min(batch_size, n)
    m_total = som.n_neurons
    u_flat = som.u_matrix.reshape(-1)
    hit_flat = som.hit_grid.reshape(-1)
    max_log_hit = max(math.log1p(int(hit_flat.max())), 1.0)

    grouped: dict[int, list[int]] = {}
    for idx, bmu in enumerate(cand_bmus.tolist()):
        grouped.setdefault(int(bmu), []).append(idx)

    queues: dict[int, list[int]] = {}
    neuron_quality = np.zeros(m_total, dtype=np.float64)
    for u, idxs in grouped.items():
        idx_arr = np.asarray(idxs, dtype=np.int64)
        if scores_arr is not None:
            order = np.lexsort((cand_dists[idx_arr], -scores_arr[idx_arr]))
            queues[u] = [int(idx_arr[k]) for k in order]
            neuron_quality[u] = 0.75 * float(scores_arr[idx_arr].max()) + 0.25 * float(u_flat[u])
        else:
            asc = np.argsort(cand_dists[idx_arr], kind="stable")
            medoid = [int(idx_arr[asc[0]])]
            spread = [int(idx_arr[k]) for k in asc[:0:-1]]
            queues[u] = medoid + spread
            neuron_quality[u] = (
                0.65 * (math.log1p(int(hit_flat[u])) / max_log_hit) + 0.35 * float(u_flat[u])
            )

    neighbors: list[list[int]] = [[] for _ in range(m_total)]
    for r in range(som.rows):
        for c in range(som.cols):
            u = r * som.cols + c
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < som.rows and 0 <= nc < som.cols:
                        neighbors[u].append(nr * som.cols + nc)

    seed_counts = np.bincount(seed_bmus, minlength=m_total).astype(np.float64)
    picked_counts = np.zeros(m_total, dtype=np.float64)
    cursors = {u: 0 for u in queues}
    selected: list[int] = []

    while len(selected) < batch_size:
        active = [u for u, q in queues.items() if cursors[u] < len(q)]
        if not active:
            break
        direct_cov = seed_counts + picked_counts
        uncovered = [u for u in active if direct_cov[u] == 0.0]
        pool = uncovered if uncovered else active

        best_u = pool[0]
        best_priority = -1.0
        for u in pool:
            nb = neighbors[u]
            nb_cov = float(direct_cov[nb].mean()) if nb else 0.0
            eff_cov = float(direct_cov[u]) + 0.25 * nb_cov
            priority = (1.0 + float(neuron_quality[u])) / (1.0 + eff_cov)
            if priority > best_priority:
                best_priority = priority
                best_u = u

        selected.append(queues[best_u][cursors[best_u]])
        cursors[best_u] += 1
        picked_counts[best_u] += 1.0

    return selected
