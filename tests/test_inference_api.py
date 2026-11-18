"""inference-export spec scenarios."""

from __future__ import annotations

import io

import numpy as np
import rasterio


def train_rf(client, pid):
    resp = client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 30}})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestInference:
    def test_predict_full_image(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        resp = client.post(f"/projects/{project['id']}/predict", json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["grid_shape"] == [8, 8]
        assert body["classes"] == ["water", "vegetation"]
        hard = np.asarray(body["hard_map"])
        prob = np.asarray(body["probability_map"])
        assert hard.shape == (8, 8)
        assert prob.shape == (2, 8, 8)
        assert np.allclose(prob.sum(axis=0), 1.0, atol=1e-5)
        # left half water (0), right half vegetation (1)
        assert (hard[:, :4] == 0).all()
        assert (hard[:, 4:] == 1).all()
        assert "/download/hard" in body["exports"]["hard"]

    def test_predict_region(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        resp = client.post(
            f"/projects/{project['id']}/predict",
            json={"region": {"x0": 32, "y0": 0, "x1": 64, "y1": 32}},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["grid_shape"] == [4, 4]
        hard = np.asarray(body["hard_map"])
        assert hard.shape == (4, 4)
        assert (hard == 1).all()  # region is all vegetation

    def test_predict_invalid_region(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        resp = client.post(
            f"/projects/{project['id']}/predict",
            json={"region": {"x0": 0, "y0": 0, "x1": 999, "y1": 999}},
        )
        assert resp.status_code == 422

    def test_predict_without_model_409(self, client, project, dataset):
        assert client.post(f"/projects/{project['id']}/predict", json={}).status_code == 409

    def test_predict_no_maps_option(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        resp = client.post(f"/projects/{project['id']}/predict", json={"include_maps": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["hard_map"] is None
        assert body["probability_map"] is None

    def test_download_hard_geotiff(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        client.post(f"/projects/{project['id']}/predict", json={})
        resp = client.get(f"/projects/{project['id']}/download/hard")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/tiff")
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            assert ds.driver == "GTiff"
            assert ds.count == 1
            assert ds.crs.to_string() == "EPSG:32631"
            arr = ds.read(1)
            # Patch cells are painted over their pixel windows on the source
            # grid: 8x8 cells of an 8 px patch tile a 64x64 scene exactly.
            assert arr.shape == (64, 64)
            assert ds.nodata == 65535
            assert set(np.unique(arr)) <= {0, 1}
            assert (arr[:, :32] == 0).all() and (arr[:, 32:] == 1).all()
            assert ds.tags()["resolution"] == "patch-cells"

    def test_download_probability_geotiff(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        client.post(f"/projects/{project['id']}/predict", json={})
        resp = client.get(f"/projects/{project['id']}/download/probability")
        assert resp.status_code == 200
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            assert ds.count == 2
            assert ds.dtypes[0] == "float32"
            assert (ds.height, ds.width) == (64, 64)
            assert ds.nodata == -9999.0
            arr = ds.read()
            assert np.allclose(arr.sum(axis=0), 1.0, atol=1e-5)
            assert ds.descriptions == ("water", "vegetation")

    def test_download_auto_runs_inference(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        # no explicit /predict first — download should infer + export on demand
        resp = client.get(f"/projects/{project['id']}/download/hard")
        assert resp.status_code == 200
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            assert ds.read(1).shape == (64, 64)

    def test_download_unknown_type_404(self, client, project):
        assert client.get(f"/projects/{project['id']}/download/bogus").status_code == 404

    def test_download_without_model_409(self, client, project, dataset):
        assert client.get(f"/projects/{project['id']}/download/hard").status_code == 409

    def test_exports_listing(self, client, project, dataset, labeled):
        train_rf(client, project["id"])
        client.post(f"/projects/{project['id']}/predict", json={})
        resp = client.get(f"/projects/{project['id']}/exports")
        assert resp.status_code == 200
        types = {e["type"] for e in resp.json()}
        # inference now also writes an uncertainty export for the map layers
        assert types == {"hard", "probability", "uncertainty"}
