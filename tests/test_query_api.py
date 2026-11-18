"""active-learning-query spec scenarios."""

from __future__ import annotations

from .conftest import point_label


def train_rf(client, pid):
    resp = client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 30}})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestQuery:
    def test_cold_start_diversity(self, client, project, dataset):
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "diversity", "batch_size": 5, "include_embedding": True},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["batch_size"] == 5
        assert len(body["samples"]) == 5
        s = body["samples"][0]
        assert "coords" in s and s["coords"]["x1"] > s["coords"]["x0"]
        assert s["geo_coords"] is not None and s["geo_coords"]["crs"] == "EPSG:32631"
        assert s["embedding"] is not None and len(s["embedding"]) == 16
        ids = [x["sample_id"] for x in body["samples"]]
        assert len(set(ids)) == 5

    def test_uncertainty_requires_model(self, client, project, dataset):
        resp = client.post(f"/projects/{project['id']}/query", json={"strategy": "uncertainty"})
        assert resp.status_code == 409

    def test_uncertainty_ordered(self, client, project, dataset):
        # label only a few patches so uncertainty varies across the grid
        labels = [point_label(4, 4, "water"), point_label(12, 4, "water"),
                  point_label(60, 60, "vegetation"), point_label(52, 60, "vegetation"),
                  point_label(4, 12, "water"), point_label(60, 52, "vegetation"),
                  point_label(12, 12, "water"), point_label(52, 52, "vegetation")]
        resp = client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
        assert resp.status_code == 201
        train_rf(client, project["id"])

        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "uncertainty", "batch_size": 7, "method": "entropy"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["strategy"] == "uncertainty"
        samples = body["samples"]
        assert len(samples) == 7
        uncs = [s["uncertainty"] for s in samples]
        assert uncs == sorted(uncs, reverse=True)  # ordered by uncertainty
        for s in samples:
            assert s["prediction"] in ("water", "vegetation")
            assert 0.0 <= s["confidence"] <= 1.0
            assert 0.0 <= s["uncertainty"] <= 1.0
            assert s["embedding"] is None  # not requested

    def test_all_uncertainty_methods(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        for method in ("least_confidence", "margin", "entropy"):
            resp = client.post(
                f"/projects/{project['id']}/query",
                json={"strategy": "uncertainty", "method": method, "batch_size": 3, "exclude_labeled": False},
            )
            assert resp.status_code == 200, resp.text
            assert len(resp.json()["samples"]) == 3

    def test_diversity_after_training(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "diversity", "batch_size": 4, "exclude_labeled": False},
        )
        assert resp.status_code == 200
        assert len(resp.json()["samples"]) == 4

    def test_hybrid(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "hybrid", "batch_size": 6, "exclude_labeled": False},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["samples"]) == 6
        assert len({s["sample_id"] for s in body["samples"]}) == 6
        assert all(s["uncertainty"] is not None for s in body["samples"])

    def test_batch_size_capped_by_pool(self, client, project, dataset):
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "diversity", "batch_size": 500},
        )
        assert resp.status_code == 200
        assert resp.json()["batch_size"] == 64  # 8x8 grid total

    def test_exclude_labeled(self, client, project, dataset, labeled):
        # every patch labeled -> empty pool
        resp = client.post(
            f"/projects/{project['id']}/query", json={"strategy": "diversity", "batch_size": 5}
        )
        assert resp.status_code == 200
        assert resp.json()["samples"] == []
        resp = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "diversity", "batch_size": 5, "exclude_labeled": False},
        )
        assert len(resp.json()["samples"]) == 5

    def test_query_no_dataset_409(self, client, project):
        resp = client.post(f"/projects/{project['id']}/query", json={"strategy": "diversity"})
        assert resp.status_code == 409
