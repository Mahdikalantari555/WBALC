"""Unit tests for active learning strategy math."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.al_service import (
    kcenter_greedy,
    select_hybrid,
    select_uncertainty,
    uncertainty_scores,
)


class TestUncertainty:
    def test_least_confidence(self):
        probs = np.array([[0.9, 0.1], [0.5, 0.5], [0.7, 0.3]])
        scores = uncertainty_scores(probs, "least_confidence")
        assert scores[1] > scores[2] > scores[0]
        assert scores[1] == pytest.approx(0.5)

    def test_margin(self):
        probs = np.array([[0.9, 0.1], [0.5, 0.5], [0.7, 0.3]])
        scores = uncertainty_scores(probs, "margin")
        assert scores[1] == pytest.approx(1.0)
        assert scores[0] == pytest.approx(0.2)
        assert scores[1] > scores[2] > scores[0]

    def test_entropy(self):
        probs = np.array([[1.0, 0.0], [0.5, 0.5]])
        scores = uncertainty_scores(probs, "entropy")
        assert scores[0] == pytest.approx(0.0, abs=1e-9)
        assert scores[1] == pytest.approx(1.0)

    def test_multiclass_entropy_normalized(self):
        k = 4
        probs = np.full((1, k), 1.0 / k)
        assert uncertainty_scores(probs, "entropy")[0] == pytest.approx(1.0)

    def test_unknown_method(self):
        with pytest.raises(ValueError):
            uncertainty_scores(np.array([[0.5, 0.5]]), "bogus")


class TestSelection:
    def test_uncertainty_order_and_batch(self):
        scores = np.array([0.1, 0.9, 0.5, 0.7])
        assert select_uncertainty(scores, 3) == [1, 3, 2]
        assert len(select_uncertainty(scores, 100)) == 4

    def test_kcenter_spread(self):
        # two tight clusters; core-set should pick from both before doubling up
        rng = np.random.default_rng(0)
        a = rng.normal(0, 0.01, (10, 2))
        b = rng.normal(10, 0.01, (10, 2)) + np.array([10, 10])
        X = np.vstack([a, b])
        picked = kcenter_greedy(X, 2)
        clusters = {int(p >= 10) for p in picked}
        assert clusters == {0, 1}

    def test_kcenter_batch_cap_and_empty(self):
        X = np.random.default_rng(1).normal(size=(5, 3))
        assert len(kcenter_greedy(X, 50)) == 5
        assert kcenter_greedy(np.zeros((0, 3)), 5) == []

    def test_kcenter_with_seeds_avoids_covered_region(self):
        X = np.array([[0.0, 0.0], [0.1, 0.0], [10.0, 10.0]])
        seeds = np.array([[0.0, 0.1]])
        picked = kcenter_greedy(X, 1, seeds)
        assert picked == [2]

    def test_hybrid_combines_both(self):
        rng = np.random.default_rng(2)
        X = rng.normal(size=(40, 4))
        scores = rng.uniform(size=40)
        picked = select_hybrid(scores, X, 5, pool_multiplier=4)
        assert len(picked) == 5
        assert len(set(picked)) == 5
        # every pick comes from the top-20 uncertainty pool
        pool = set(select_uncertainty(scores, 20))
        assert set(picked) <= pool
