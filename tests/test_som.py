"""Unit and API tests for the Kohonen Self-Organizing Map (SOM) capability."""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.al_service import select_som
from app.services.som_service import (
    default_som_shape,
    fit_som,
    normalized_band_profiles,
)
from .conftest import point_label


class TestSomService:
    def test_default_shape_bounds(self):
        assert default_som_shape(1) == (2, 2)
        assert default_som_shape(64) == (6, 6)
        r, c = default_som_shape(10_000, max_side=10)
        assert r == 10 and c == 10

    def test_fit_separates_clusters_and_is_deterministic(self):
        rng = np.random.default_rng(11)
        water = rng.normal([10.0, 20.0, 100.0, 120.0], 1.0, size=(25, 4))
        veg = rng.normal([80.0, 90.0, 30.0, 150.0], 1.0, size=(25, 4))
        X = np.vstack([water, veg])

        som1 = fit_som(X, rows=4, cols=4, epochs=40, random_state=42)
        som2 = fit_som(X, rows=4, cols=4, epochs=40, random_state=42)

        assert np.allclose(som1.weights, som2.weights)
        assert np.array_equal(som1.bmus, som2.bmus)
        assert som1.hit_grid.shape == (4, 4)
        assert int(som1.hit_grid.sum()) == 50
        assert som1.u_matrix.shape == (4, 4)
        assert 0.0 <= float(som1.u_matrix.min()) <= float(som1.u_matrix.max()) <= 1.0
        assert som1.quantization_error >= 0.0
        assert 0.0 <= som1.topographic_error <= 1.0

        # Clusters should map to disjoint BMU sets
        water_bmus = set(som1.bmus[:25].tolist())
        veg_bmus = set(som1.bmus[25:].tolist())
        assert water_bmus.isdisjoint(veg_bmus)

        # transform() reproduces training BMUs identically
        proj_bmus, proj_dists = som1.transform(X)
        assert np.array_equal(proj_bmus, som1.bmus)
        assert np.allclose(proj_dists, som1.bmu_dists)

    def test_constant_and_tiny_inputs(self):
        const_X = np.ones((8, 4), dtype=np.float64) * 7.0
        som = fit_som(const_X, rows=2, cols=2, epochs=10)
        assert np.isfinite(som.weights).all()
        assert np.isfinite(som.u_matrix).all()
        assert int(som.hit_grid.sum()) == 8

        single = np.array([[1.0, 2.0, 3.0]])
        som_single = fit_som(single, rows=2, cols=2, epochs=5)
        assert int(som_single.hit_grid.sum()) == 1

        one_dim = np.linspace(0.0, 10.0, 12).reshape(-1, 1)
        som_1d = fit_som(one_dim, rows=2, cols=3, epochs=15)
        assert som_1d.weights.shape == (6, 1)

        with pytest.raises(ValueError):
            fit_som(np.zeros((0, 4)))

    def test_normalized_band_profiles(self):
        X = np.array(
            [
                [10.0, 20.0, 30.0, 1.0],
                [50.0, 60.0, 70.0, 2.0],
                [90.0, 100.0, 110.0, 3.0],
            ]
        )
        som = fit_som(X, rows=2, cols=2, epochs=20)
        means, profiles = normalized_band_profiles(X, som.weights_denorm, bands=3)
        assert means.shape == (4, 3)
        assert profiles.shape == (4, 3)
        assert (profiles >= 0.0).all() and (profiles <= 1.0).all()


class TestSomSelection:
    def test_cold_start_spreads_across_clusters(self):
        rng = np.random.default_rng(3)
        a = rng.normal(-10.0, 0.05, size=(12, 3))
        b = rng.normal(10.0, 0.05, size=(12, 3))
        X = np.vstack([a, b])
        picked = select_som(X, batch_size=2, rows=3, cols=3, epochs=30)
        assert len(picked) == 2
        clusters = {int(p >= 12) for p in picked}
        assert clusters == {0, 1}

    def test_seeds_steer_away_from_labeled_cluster(self):
        rng = np.random.default_rng(5)
        a = rng.normal(0.0, 0.05, size=(10, 3))
        b = rng.normal(20.0, 0.05, size=(10, 3))
        X = np.vstack([a, b])
        seeds = rng.normal(0.0, 0.05, size=(4, 3))
        picked = select_som(X, batch_size=1, seed_embeddings=seeds, rows=3, cols=3, epochs=30)
        assert len(picked) == 1
        assert picked[0] >= 10  # selects from uncovered cluster b

    def test_uncertainty_guided_som(self):
        rng = np.random.default_rng(9)
        X = rng.normal(size=(30, 4))
        scores = np.linspace(0.05, 0.95, 30)
        picked = select_som(X, batch_size=6, scores=scores, rows=3, cols=3, epochs=25)
        assert len(picked) == 6
        assert len(set(picked)) == 6
        # Mean uncertainty of SOM-selected samples should exceed pool average
        assert float(scores[picked].mean()) > float(scores.mean())

    def test_target_cell_and_bounds_check(self):
        rng = np.random.default_rng(12)
        X = rng.normal(size=(20, 4))
        som = fit_som(X, rows=3, cols=3, epochs=20, random_state=42)
        active_bmu = int(som.bmus[0])
        r, c = divmod(active_bmu, 3)

        picked = select_som(X, batch_size=10, rows=3, cols=3, epochs=20, random_state=42, target_cell=(r, c))
        expected = set(np.where(som.bmus == active_bmu)[0].tolist())
        assert len(picked) > 0
        assert set(picked) <= expected

        with pytest.raises(ValueError):
            select_som(X, batch_size=2, rows=3, cols=3, target_cell=(3, 0))

    def test_empty_and_batch_cap(self):
        X = np.random.default_rng(0).normal(size=(5, 3))
        assert select_som(np.zeros((0, 3)), 4) == []
        assert select_som(X, 0) == []
        assert len(select_som(X, 50, rows=2, cols=2)) == 5


class TestSomApi:
    def test_som_explorer_cold_start_get_and_post(self, client, project, dataset):
        resp = client.get(f"/projects/{project['id']}/som?rows=5&cols=4&epochs=30")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == project["id"]
        assert body["dataset_id"] == dataset["id"]
        assert body["rows"] == 5 and body["cols"] == 4
        assert body["total_patches"] == 64
        assert body["labeled_patches"] == 0
        assert body["model_iteration"] is None
        assert body["bands"] == 4
        assert len(body["cells"]) == 20
        assert sum(c["hit_count"] for c in body["cells"]) == 64
        assert len(body["u_matrix"]) == 5 and len(body["u_matrix"][0]) == 4
        for cell in body["cells"]:
            assert len(cell["band_means"]) == 4
            assert len(cell["band_profile"]) == 4
            assert 0.0 <= cell["u_value"] <= 1.0

        post_resp = client.post(
            f"/projects/{project['id']}/som",
            json={"rows": 5, "cols": 4, "epochs": 30},
        )
        assert post_resp.status_code == 200
        assert post_resp.json()["hit_grid"] == body["hit_grid"]

    def test_som_explorer_with_labels_and_trained_model(self, client, project, dataset):
        pid = project["id"]
        labels = [
            point_label(4, 4, "water"),
            point_label(12, 4, "water"),
            point_label(4, 12, "water"),
            point_label(12, 12, "water"),
            point_label(60, 60, "vegetation"),
            point_label(52, 60, "vegetation"),
            point_label(60, 52, "vegetation"),
            point_label(52, 52, "vegetation"),
        ]
        assert client.post(f"/projects/{pid}/labels", json={"labels": labels}).status_code == 201
        assert (
            client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 30}}).status_code
            == 201
        )

        resp = client.get(f"/projects/{pid}/som?rows=4&cols=4")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["labeled_patches"] == 8
        assert body["model_iteration"] is not None
        populated = [c for c in body["cells"] if c["hit_count"] > 0]
        assert len(populated) >= 2
        for c in populated:
            assert c["predicted_class"] in ("water", "vegetation")
            assert 0.0 <= c["mean_confidence"] <= 1.0
            assert 0.0 <= c["mean_uncertainty"] <= 1.0

        # Water and vegetation labels should organize into separate dominant neurons
        labeled_cells = [c for c in populated if c["labeled_count"] > 0]
        assert {c["dominant_label"] for c in labeled_cells} == {"water", "vegetation"}

    def test_som_query_cold_start_and_targeted_cell_consistency(self, client, project, dataset):
        pid = project["id"]
        # Partial labels so we test SOM consistency even when some patches are excluded!
        labels = [point_label(4, 4, "water"), point_label(60, 60, "vegetation")]
        assert client.post(f"/projects/{pid}/labels", json={"labels": labels}).status_code == 201

        som_body = client.get(f"/projects/{pid}/som?rows=4&cols=4&epochs=40").json()
        target = next(c for c in som_body["cells"] if c["unlabeled_count"] >= 2)

        q_cell = client.post(
            f"/projects/{pid}/query",
            json={
                "strategy": "som",
                "batch_size": 10,
                "som_rows": 4,
                "som_cols": 4,
                "som_epochs": 40,
                "som_cell": [target["row"], target["col"]],
            },
        )
        assert q_cell.status_code == 200, q_cell.text
        q_samples = q_cell.json()["samples"]
        assert len(q_samples) == target["unlabeled_count"]
        returned_ids = {s["sample_id"] for s in q_samples}
        assert returned_ids <= set(target["sample_ids"])

        # Full SOM batch query
        q_full = client.post(
            f"/projects/{pid}/query",
            json={"strategy": "som", "batch_size": 8, "som_rows": 4, "som_cols": 4},
        )
        assert q_full.status_code == 200
        assert q_full.json()["strategy"] == "som"
        assert q_full.json()["method"] is None
        assert len(q_full.json()["samples"]) == 8

    def test_som_errors(self, client, project, dataset):
        assert client.get("/projects/9999/som").status_code == 404
        empty_proj = client.post(
            "/projects", json={"name": "Empty", "classes": ["a", "b"]}
        ).json()
        assert client.get(f"/projects/{empty_proj['id']}/som").status_code == 409
        bad_cell = client.post(
            f"/projects/{project['id']}/query",
            json={"strategy": "som", "som_rows": 4, "som_cols": 4, "som_cell": [9, 9]},
        )
        assert bad_cell.status_code == 422


class TestUnsupervisedSom:
    def test_pixel_level_unsupervised_classification_without_labels(self, client, project, dataset):
        # Zero labels and zero supervised training runs!
        resp = client.post(
            f"/projects/{project['id']}/som/classify",
            json={"rows": 4, "cols": 4, "n_clusters": 2, "epochs": 35},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["n_clusters"] == 2
        assert body["resolution"] == "pixel"
        assert body["shape"] == [64, 64]
        assert body["total_valid"] == 64 * 64
        assert body["nodata_count"] == 0
        assert sum(c["pixel_count"] for c in body["clusters"]) == 64 * 64
        assert sum(c["fraction"] for c in body["clusters"]) == pytest.approx(1.0)

        cmap = np.asarray(body["cluster_map"])
        assert cmap.shape == (64, 64)
        left_cls = int(np.bincount(cmap[:, :32].ravel()).argmax())
        right_cls = int(np.bincount(cmap[:, 32:].ravel()).argmax())
        assert left_cls != right_cls
        assert float((cmap[:, :32] == left_cls).mean()) > 0.99
        assert float((cmap[:, 32:] == right_cls).mean()) > 0.99

        # Download the exported GeoTIFF and verify exact reference-grid alignment.
        source = client.get(f"/projects/{project['id']}/dataset/{dataset['id']}/file")
        with rasterio.open(io.BytesIO(source.content)) as reference:
            expected_transform, expected_bounds = reference.transform, reference.bounds
        dl = client.get(f"/projects/{project['id']}/download/som")
        assert dl.status_code == 200
        with rasterio.open(io.BytesIO(dl.content)) as ds:
            assert ds.driver == "GTiff"
            assert ds.width == 64 and ds.height == 64
            assert ds.crs.to_string() == "EPSG:32631"
            assert ds.transform == expected_transform
            assert ds.bounds == expected_bounds
            assert ds.nodata == 65535
            assert 0 in ds.colormap(1)
            arr = ds.read(1)
            assert np.array_equal(arr, cmap)

        exports = client.get(f"/projects/{project['id']}/exports").json()
        assert any(e["type"] == "som" and e["training_run_id"] is None for e in exports)

    def test_raw_neurons_patch_mode_region_and_auto_download(self, client, project, dataset):
        pid = project["id"]
        # Auto-download on a brand-new dataset before calling /som/classify
        auto_dl = client.get(f"/projects/{pid}/som/download")
        assert auto_dl.status_code == 200
        with rasterio.open(io.BytesIO(auto_dl.content)) as ds:
            assert ds.width == 64 and ds.height == 64

        # Raw SOM neurons (3x3 = 9 unsupervised clusters) in patch mode
        patch_resp = client.post(
            f"/projects/{pid}/som/classify",
            json={"rows": 3, "cols": 3, "resolution": "patch", "epochs": 25},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        pbody = patch_resp.json()
        assert pbody["n_clusters"] == 9
        assert pbody["shape"] == [8, 8]

        # Region crop + include_map=False
        reg_resp = client.post(
            f"/projects/{pid}/som/classify",
            json={
                "rows": 2,
                "cols": 2,
                "region": {"x0": 0, "y0": 0, "x1": 32, "y1": 24},
                "include_map": False,
            },
        )
        assert reg_resp.status_code == 200
        assert reg_resp.json()["shape"] == [24, 32]
        assert reg_resp.json()["cluster_map"] is None

    def test_nodata_preserved_and_validation_errors(self, client, project):
        pid = project["id"]
        rng = np.random.default_rng(19)
        arr = rng.normal(100.0, 15.0, size=(3, 32, 32)).astype(np.float32)
        arr[:, :4, :] = -9999.0  # 4x32 = 128 nodata pixels
        buf = io.BytesIO()
        with rasterio.open(
            buf,
            "w",
            driver="GTiff",
            height=32,
            width=32,
            count=3,
            dtype="float32",
            nodata=-9999.0,
            crs="EPSG:32631",
            transform=from_origin(500000, 4649776, 10, 10),
        ) as dst:
            dst.write(arr)
        up = client.post(
            f"/projects/{pid}/upload",
            files={"file": ("nodata_scene.tif", buf.getvalue(), "image/tiff")},
        ).json()

        res = client.post(
            f"/projects/{pid}/som/classify",
            json={"dataset_id": up["id"], "rows": 2, "cols": 2, "epochs": 20},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["nodata_count"] == 128
        assert body["total_valid"] == 32 * 32 - 128
        cmap = np.asarray(body["cluster_map"])
        assert (cmap[:4, :] == 65535).all()
        assert (cmap[4:, :] < 4).all()

        # Validation: n_clusters > rows*cols -> 422, out-of-bounds region -> 422
        assert (
            client.post(
                f"/projects/{pid}/som/classify",
                json={"rows": 2, "cols": 2, "n_clusters": 10},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/projects/{pid}/som/classify",
                json={"region": {"x0": 0, "y0": 0, "x1": 999, "y1": 999}},
            ).status_code
            == 422
        )
