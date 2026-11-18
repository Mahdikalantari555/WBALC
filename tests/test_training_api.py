"""model-training spec scenarios."""

from __future__ import annotations

from pathlib import Path

from .conftest import point_label


class TestTraining:
    def test_train_rf_and_metrics(self, client, project, dataset, labeled):
        resp = client.post(
            f"/projects/{project['id']}/train",
            json={"model_type": "rf", "params": {"n_estimators": 40}},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["model_type"] == "rf"
        assert body["n_samples"] == 64
        assert Path(body["checkpoint"]).exists()  # checkpoint artifact stored

        m = body["metrics"]
        assert m["accuracy"] > 0.9  # separable synthetic data
        assert 0 <= m["f1_macro"] <= 1
        assert 0 <= m["f1_weighted"] <= 1
        assert len(m["confusion_matrix"]) == 2
        assert len(m["confusion_matrix"][0]) == 2
        assert set(m["per_class"]) == {"water", "vegetation"}
        assert {"precision", "recall", "f1", "support"} <= set(m["per_class"]["water"])

    def test_train_lightgbm(self, client, project, dataset, labeled):
        resp = client.post(
            f"/projects/{project['id']}/train",
            json={"model_type": "lightgbm", "params": {"n_estimators": 30, "min_child_samples": 5}},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["model_type"] == "lightgbm"
        assert Path(body["checkpoint"]).exists()
        assert body["metrics"]["accuracy"] > 0.9

    def test_metrics_endpoint(self, client, project, dataset, labeled):
        client.post(f"/projects/{project['id']}/train", json={"model_type": "rf", "params": {"n_estimators": 20}})
        resp = client.get(f"/projects/{project['id']}/metrics")
        assert resp.status_code == 200
        m = resp.json()
        for field in ("accuracy", "f1_macro", "f1_weighted", "confusion_matrix", "per_class"):
            assert field in m

    def test_metrics_404_before_training(self, client, project, dataset):
        assert client.get(f"/projects/{project['id']}/metrics").status_code == 404

    def test_checkpoints_per_iteration(self, client, project, dataset, labeled):
        r1 = client.post(f"/projects/{project['id']}/train", json={"model_type": "rf", "params": {"n_estimators": 10}})
        # add a new label at a higher iteration, then retrain
        client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "water", iteration=1))
        r2 = client.post(f"/projects/{project['id']}/train", json={"model_type": "rf", "params": {"n_estimators": 10}})
        b1, b2 = r1.json(), r2.json()
        assert b2["iteration"] == b1["iteration"] + 1
        assert b1["checkpoint"] != b2["checkpoint"]
        assert Path(b1["checkpoint"]).exists() and Path(b2["checkpoint"]).exists()

        history = client.get(f"/projects/{project['id']}/metrics/history").json()
        assert len(history) == 2
        specific = client.get(f"/projects/{project['id']}/metrics?iteration={b1['iteration']}").json()
        assert specific["id"] == b1["id"]

    def test_training_uses_current_labels(self, client, project, dataset, labeled):
        # correct one water patch to vegetation; retrain must see 63 usable unique patches still
        client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "vegetation", iteration=2))
        resp = client.post(f"/projects/{project['id']}/train", json={"model_type": "rf", "params": {"n_estimators": 10}})
        assert resp.status_code == 201
        assert resp.json()["n_samples"] == 64  # corrected, not duplicated

    def test_auto_train_on_labels(self, client, project, dataset):
        labels = []
        for row in range(4):
            for col in range(8):
                cls = "water" if col < 4 else "vegetation"
                labels.append(point_label(col * 8 + 4, row * 8 + 4, cls))
        resp = client.post(
            f"/projects/{project['id']}/labels",
            json={"labels": labels, "auto_train": True, "model_type": "rf"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["training"] is not None
        assert body["training"]["n_samples"] == 32
        assert body["training_error"] is None

    def test_auto_train_insufficient_reports_error(self, client, project, dataset):
        resp = client.post(
            f"/projects/{project['id']}/labels",
            json={"labels": [point_label(4, 4, "water")], "auto_train": True},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["training"] is None
        assert "2 classes" in body["training_error"]

    def test_train_without_labels_409(self, client, project, dataset):
        resp = client.post(f"/projects/{project['id']}/train", json={"model_type": "rf"})
        assert resp.status_code == 409

    def test_train_without_dataset_409(self, client, project):
        resp = client.post(f"/projects/{project['id']}/train", json={"model_type": "rf"})
        assert resp.status_code == 409

    def test_train_invalid_model_422(self, client, project, dataset, labeled):
        resp = client.post(f"/projects/{project['id']}/train", json={"model_type": "cnn"})
        assert resp.status_code == 422
