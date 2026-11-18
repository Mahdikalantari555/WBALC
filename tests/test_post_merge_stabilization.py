"""Post-merge stabilization: regression tests for every confirmed defect.

Each test is named in ``openspec/changes/stabilize-post-merge/audit.md`` (D1-D16).
Fixtures are synthetic; nothing is downloaded and every test is deterministic.
"""

from __future__ import annotations

import io
import json

import joblib
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tests.conftest import point_label


def _geotiff(
    data: np.ndarray,
    transform=None,
    crs: str | None = "EPSG:32631",
    nodata: float | None = None,
) -> bytes:
    buffer = io.BytesIO()
    kwargs = {}
    if crs is not None:
        kwargs["crs"] = crs
    if transform is not None:
        kwargs["transform"] = transform
    if nodata is not None:
        kwargs["nodata"] = nodata
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype="float32",
        **kwargs,
    ) as dst:
        dst.write(data)
    return buffer.getvalue()


def _scene(h: int = 64, w: int = 64, collar: int = 0, nodata: float | None = None) -> bytes:
    """Left `collar` columns nodata, then a water band, then vegetation."""
    rng = np.random.default_rng(3)
    data = np.zeros((4, h, w), dtype=np.float32)
    data[:, :, :collar] = 0.0
    rest = w - collar
    half = collar + rest // 2
    data[:, :, collar:half] = np.array([10, 20, 100, 120], dtype=np.float32)[:, None, None] + rng.normal(
        0, 2, (4, h, half - collar)
    )
    data[:, :, half:] = np.array([80, 90, 30, 150], dtype=np.float32)[:, None, None] + rng.normal(
        0, 2, (4, h, w - half)
    )
    if nodata is None and collar:
        nodata = 0.0  # a collar is only nodata when the raster declares it
    return _geotiff(data, from_origin(500000, 4649776, 10, 10), nodata=nodata)


def _upload(client, pid: int, payload: bytes, name: str = "scene.tif") -> dict:
    resp = client.post(f"/projects/{pid}/upload", files={"file": (name, payload, "image/tiff")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _labels(client, pid: int, items) -> None:
    resp = client.post(f"/projects/{pid}/labels", json={"labels": items})
    assert resp.status_code == 201, resp.text


def _train(client, pid: int, **body) -> dict:
    body.setdefault("model_type", "rf")
    body.setdefault("params", {"n_estimators": 10})
    resp = client.post(f"/projects/{pid}/train", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _grid_labels(dsid: int, h: int, w: int, patch: int = 8) -> list[dict]:
    labels = []
    for row in range(0, h, patch):
        for col in range(0, w, patch):
            x, y = min(col + patch // 2, w - 1), min(row + patch // 2, h - 1)
            labels.append(
                point_label(x, y, "water" if col < w // 2 else "vegetation", dataset_id=dsid)
            )
    return labels


class TestPatchExportGeometry:
    """D1/D10 — patch cells must land on their true pixel windows."""

    def test_patch_export_preserves_source_grid_on_clamped_edges(self, client, project):
        h = w = 70  # 8 px patches do not divide 70: last row/column are clamped
        ds = _upload(client, project["id"], _scene(h, w))
        _labels(client, project["id"], _grid_labels(ds["id"], h, w))
        _train(client, project["id"])

        resp = client.get(f"/projects/{project['id']}/download/hard", params={"dataset_id": ds["id"]})
        assert resp.status_code == 200, resp.text
        with rasterio.open(io.BytesIO(resp.content)) as out:
            assert (out.height, out.width) == (h, w)
            assert out.crs.to_string() == "EPSG:32631"
            assert out.transform.a == pytest.approx(10.0)
            assert out.transform.e == pytest.approx(-10.0)
            # no overhang past the source extent
            assert out.bounds.left == pytest.approx(500000.0)
            assert out.bounds.top == pytest.approx(4649776.0)
            assert out.bounds.right == pytest.approx(500000.0 + 10 * w)
            assert out.bounds.bottom == pytest.approx(4649776.0 - 10 * h)

            grid = json.loads(out.tags()["grid"])
            assert out.tags()["resolution"] == "patch-cells"
            assert grid["cells"][-1]["x1"] == w and grid["cells"][-1]["y1"] == h
            values = out.read(1)
            for cell in grid["cells"]:
                window = values[cell["y0"] : cell["y1"], cell["x0"] : cell["x1"]]
                # block fill: one class per cell, no interpolation
                assert window.min() == window.max()

    def test_patch_export_marks_stride_gaps_nodata(self, client, settings, project):
        """Patch 4, stride 8: every other 4 px strip is unclassified -> nodata."""
        settings.patch_size = 4
        settings.stride = 8
        client.app.state.settings.patch_size = 4
        client.app.state.settings.stride = 8
        ds = _upload(client, project["id"], _scene(64, 64))
        _labels(client, project["id"], _grid_labels(ds["id"], 64, 64, patch=4))
        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/download/hard", params={"dataset_id": ds["id"]})
        with rasterio.open(io.BytesIO(resp.content)) as out:
            assert (out.height, out.width) == (64, 64)
            values = out.read(1)
            # columns 4..7, 12..15, ... are covered by no cell
            assert (values[:, 4:8] == out.nodata).all()
            assert (values[:, 0:4] != out.nodata).any()

    def test_region_export_keeps_window_transform(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.post(
            f"/projects/{project['id']}/predict",
            json={"region": {"x0": 8, "y0": 8, "x1": 40, "y1": 24}},
        )
        assert resp.status_code == 200, resp.text
        got = client.get(f"/projects/{project['id']}/download/hard")
        with rasterio.open(io.BytesIO(got.content)) as out:
            assert (out.height, out.width) == (16, 32)
            assert out.transform.c == pytest.approx(500000.0 + 10 * 8)
            assert out.transform.f == pytest.approx(4649776.0 - 10 * 8)
            grid = json.loads(out.tags()["grid"])
            # cell windows are recorded in absolute source pixels; the region
            # tag says where the raster itself starts
            assert grid["region"] == {"x0": 8, "y0": 8}
            assert all(8 <= cell["y0"] < 24 and 8 <= cell["x0"] < 40 for cell in grid["cells"])


class TestInvalidMasks:
    """D2 — probability, hard and uncertainty must share one mask."""

    def test_predict_probability_map_masks_invalid_cells(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64, collar=16))
        _labels(client, pid, _grid_labels(ds["id"], 64, 64))
        _train(client, pid)

        body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
        valid = np.asarray(body["valid_map"])
        hard = np.asarray(body["hard_map"])
        assert not valid[:, :2].any()  # nodata collar
        assert (hard[~valid] == 65535).all()
        unc = np.asarray(body["uncertainty_map"], dtype=float)
        assert np.isnan(unc[~valid]).all()
        probs = body["probability_map"]
        for row in range(0, 8):
            for col in range(0, 2):
                assert probs[0][row][col] is None and probs[1][row][col] is None
        # valid cells still carry a normalised distribution
        sums = [probs[0][r][c] + probs[1][r][c] for r in range(8) for c in range(2, 8)]
        assert all(abs(total - 1.0) < 1e-5 for total in sums)

    def test_probability_export_marks_invalid_cells(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64, collar=16))
        _labels(client, pid, _grid_labels(ds["id"], 64, 64))
        _train(client, pid)
        client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]})
        with rasterio.open(io.BytesIO(client.get(f"/projects/{pid}/download/probability").content)) as dsout:
            assert dsout.nodata == -9999.0
            assert (dsout.read(window=rasterio.windows.Window(0, 0, 16, 64)) == -9999.0).all()
            arr = dsout.read(window=rasterio.windows.Window(16, 0, 48, 64))
            assert np.allclose(arr.sum(axis=0), 1.0, atol=1e-5)

    def test_pixel_mode_masks_invalid_pixels(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64, collar=16))
        _labels(
            client,
            pid,
            [
                point_label(x, y, "water" if x < 40 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in range(4, 64, 8)
                for x in range(20, 64, 4)
            ],
        )
        _train(client, pid, resolution="pixel")
        body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
        assert body["resolution"] == "pixel"
        valid = np.asarray(body["valid_map"])
        assert valid.shape == (64, 64)
        assert not valid[:, :16].any()
        assert (np.asarray(body["hard_map"])[~valid] == 65535).all()
        assert np.isnan(np.asarray(body["uncertainty_map"], dtype=float)[~valid]).all()
        assert all(
            body["probability_map"][k][r][c] is None
            for k in (0, 1)
            for r in range(0, 64, 13)
            for c in range(0, 16, 5)
        )
        got = client.get(f"/projects/{pid}/download/hard", params={"dataset_id": ds["id"]})
        with rasterio.open(io.BytesIO(got.content)) as out:
            assert (out.height, out.width) == (64, 64)
            grid = json.loads(out.tags()["grid"])
            # a per-pixel cell list would be enormous and say nothing new
            assert "cells" not in grid and grid["cells_are_pixels"] is True
            assert out.tags()["resolution"] == "pixel"
            assert (out.read(1)[:, :16] == out.nodata).all()


class TestQueryIntegrity:
    """D3/D4 — incompatible checkpoints and invalid candidates."""

    def test_query_excludes_invalid_patches(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64, collar=16))
        # label only the valid part so training has data but the query pool has nodata
        _labels(
            client,
            pid,
            [
                point_label(col * 8 + 4, row * 8 + 4, "water" if col < 4 else "vegetation", dataset_id=ds["id"])
                for row in range(8)
                for col in range(2, 8)
            ],
        )
        _train(client, pid)
        for strategy in ("uncertainty", "diversity", "hybrid", "som"):
            resp = client.post(
                f"/projects/{pid}/query",
                json={"strategy": strategy, "batch_size": 12, "exclude_labeled": False, "dataset_id": ds["id"]},
            )
            assert resp.status_code == 200, (strategy, resp.text)
            cols = [s["coords"]["col"] for s in resp.json()["samples"]]
            assert cols, strategy
            # the nodata collar covers pixel columns 0..15 -> grid cols 0..1
            assert min(cols) >= 2, (strategy, cols)

    def test_query_rejects_or_degrades_for_pixel_checkpoint(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64))
        _labels(
            client,
            pid,
            [
                point_label(x, y, "water" if x < 32 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in range(4, 64, 8)
                for x in range(4, 64, 4)
            ],
        )
        _train(client, pid, resolution="pixel", params={"n_estimators": 5})

        for strategy in ("uncertainty", "hybrid"):
            resp = client.post(f"/projects/{pid}/query", json={"strategy": strategy, "batch_size": 4})
            assert resp.status_code == 409, resp.text
            assert "patch" in resp.json()["detail"].lower()

        for strategy in ("diversity", "som"):
            resp = client.post(
                f"/projects/{pid}/query", json={"strategy": strategy, "batch_size": 4, "exclude_labeled": False}
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["model_iteration"] is None
            assert body["notes"] and "pixel" in body["notes"][0]
            assert all(s["prediction"] is None for s in body["samples"])


class TestSomIntegrity:
    """D5/D6/D13 — SOM must ignore nodata and incompatible models."""

    def test_som_explorer_ignores_pixel_checkpoint_and_invalid_patches(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64, collar=16))
        _labels(
            client,
            pid,
            [
                point_label(x, y, "water" if x < 40 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in range(4, 64, 8)
                for x in range(20, 64, 4)
            ],
        )
        _train(client, pid, resolution="pixel", params={"n_estimators": 5})

        resp = client.get(f"/projects/{pid}/som", params={"dataset_id": ds["id"]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_iteration"] is None
        assert body["model_note"] and "pixel" in body["model_note"]
        assert body["total_patches"] == 64
        assert body["valid_patches"] == 48
        assert body["nodata_patches"] == 16
        assert sum(sum(row) for row in body["hit_grid"]) == 48
        sample_ids = [sid for cell in body["cells"] for sid in cell["sample_ids"]]
        assert len(sample_ids) == 48 and len(set(sample_ids)) == 48
        # grid cols 0..1 are the nodata collar
        assert all("_r{}_c0".format(r) not in sample_ids for r in range(8))
        assert all("_r{}_c1".format(r) not in sample_ids for r in range(8))

    def test_som_pixel_mode_uses_all_band_validity(self, client, project):
        pid = project["id"]
        data = np.zeros((4, 32, 32), dtype=np.float32)
        data[:, :, 16:] = np.array([80, 90, 30, 150], dtype=np.float32)[:, None, None]
        data[0, 10, 20] = np.nan  # one band missing at one pixel
        ds = _upload(
            client, pid, _geotiff(data, from_origin(500000, 4649776, 10, 10), nodata=0.0)
        )
        resp = client.post(
            f"/projects/{pid}/som/classify",
            json={"dataset_id": ds["id"], "resolution": "pixel", "rows": 2, "cols": 2, "epochs": 5},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_valid"] == 16 * 32 - 1
        assert body["nodata_count"] == 16 * 32 + 1
        # the partially masked pixel is nodata in the export
        got = client.get(f"/projects/{pid}/som/download", params={"dataset_id": ds["id"]})
        with rasterio.open(io.BytesIO(got.content)) as out:
            assert (out.height, out.width) == (32, 32)
            assert out.read(1)[10, 20] == out.nodata

    def test_som_patch_export_matches_source_grid(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(70, 70))
        resp = client.post(
            f"/projects/{pid}/som/classify",
            json={
                "dataset_id": ds["id"],
                "resolution": "patch",
                "rows": 2,
                "cols": 2,
                "epochs": 5,
                "patch_size": 8,
                "stride": 8,
            },
        )
        assert resp.status_code == 200, resp.text
        got = client.get(f"/projects/{pid}/som/download", params={"dataset_id": ds["id"]})
        with rasterio.open(io.BytesIO(got.content)) as out:
            assert (out.height, out.width) == (70, 70)
            assert out.crs.to_string() == "EPSG:32631"
            assert out.transform.a == pytest.approx(10.0)
            assert out.bounds.right == pytest.approx(500000.0 + 700.0)
            assert out.tags()["resolution"] == "patch-cells"


class TestCheckpoints:
    """D7 — validated loading instead of bare joblib.load."""

    def _tamper(self, checkpoint: str, mutate) -> None:
        data = joblib.load(checkpoint)
        mutate(data)
        joblib.dump(data, checkpoint)

    def test_checkpoint_validation_rejects_incompatible_payloads(self, client, project, labeled):
        pid = project["id"]
        run = _train(client, pid)
        path = run["checkpoint"]

        # 1. missing required field -> actionable 409, not 500
        self._tamper(path, lambda d: d.pop("bands"))
        resp = client.post(f"/projects/{pid}/predict", json={})
        assert resp.status_code == 409, resp.text
        assert "bands" in resp.json()["detail"]

    def test_unknown_format_and_class_drift_are_rejected(self, client, project, labeled):
        pid = project["id"]
        run = _train(client, pid)
        self._tamper(run["checkpoint"], lambda d: d.__setitem__("format", "someone-elses-format"))
        assert client.post(f"/projects/{pid}/predict", json={}).status_code == 409

        fresh = _train(client, pid)
        self._tamper(
            fresh["checkpoint"], lambda d: d.__setitem__("classes", list(reversed(d["classes"])))
        )
        resp = client.post(f"/projects/{pid}/predict", json={})
        assert resp.status_code == 409, resp.text
        assert "class" in resp.json()["detail"].lower()

    def test_legacy_v1_checkpoint_is_treated_as_patch(self, client, project, labeled):
        pid = project["id"]
        run = _train(client, pid)

        def downgrade(data):
            data.pop("feature_schema", None)
            data.pop("n_features", None)
            data["format"] = "rsal-checkpoint-v1"

        self._tamper(run["checkpoint"], downgrade)
        resp = client.post(f"/projects/{pid}/predict", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["resolution"] == "patch"

    def test_feature_schema_mismatch_is_rejected(self, client, project, labeled):
        pid = project["id"]
        run = _train(client, pid)

        def claim_pixel(data):
            data["resolution"] = "pixel"  # schema still says patch-band-stats

        self._tamper(run["checkpoint"], claim_pixel)
        resp = client.post(f"/projects/{pid}/predict", json={})
        assert resp.status_code == 409
        assert "feature schema" in resp.json()["detail"].lower()


class TestReportedContext:
    """D8 — resolution and evaluation context must be visible."""

    def test_predict_and_metrics_report_resolution(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64))
        _labels(
            client,
            pid,
            [
                point_label(x, y, "water" if x < 32 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in range(4, 64, 8)
                for x in range(4, 64, 4)
            ],
        )
        trained = _train(client, pid, resolution="pixel", evaluation_strategy="spatial")
        assert trained["resolution"] == "pixel"
        metrics = client.get(f"/projects/{pid}/metrics").json()
        assert metrics["resolution"] == "pixel"
        assert metrics["evaluation_strategy"] == "spatial"
        assert metrics["n_train"] == trained["n_samples"]
        assert "per_class_iou" in metrics

        body = client.post(f"/projects/{pid}/predict", json={}).json()
        assert body["resolution"] == "pixel"
        field = client.get(f"/projects/{pid}/predict/map", params={"layer": "hard"}).json()
        assert field["resolution"] == "pixel"
        assert field["grid"]["patch_size"] == 1

    def test_random_holdout_reports_counts_and_seed(self, client, project, labeled):
        pid = project["id"]
        trained = _train(client, pid)
        metrics = trained["metrics"]
        assert metrics["evaluation"] == "random_holdout"
        assert metrics["evaluation_strategy"] == "random"
        assert metrics["n_test"] and metrics["n_test"] > 0
        # reproducibility: same labels, same seed -> identical metrics
        again = _train(client, pid)
        assert again["metrics"]["accuracy"] == metrics["accuracy"]
        assert again["metrics"]["confusion_matrix"] == metrics["confusion_matrix"]


class TestDownloads:
    """D9 — no silently stale artifacts."""

    def test_download_regenerates_stale_export(self, client, project):
        pid = project["id"]
        ds = _upload(client, pid, _scene(64, 64))
        _labels(
            client,
            pid,
            [
                point_label(col * 8 + 4, row * 8 + 4, "water" if col < 4 else "vegetation", dataset_id=ds["id"])
                for row in range(8)
                for col in range(8)
            ],
        )
        _train(client, pid, resolution="pixel")
        assert client.post(f"/projects/{pid}/predict", json={}).status_code == 200
        _train(client, pid, resolution="patch")

        resp = client.get(f"/projects/{pid}/download/hard")
        assert resp.status_code == 200
        assert resp.headers["x-rsal-export-stale"] == "false"
        assert resp.headers["x-rsal-model-iteration"] == "1"
        with rasterio.open(io.BytesIO(resp.content)) as out:
            assert out.tags()["resolution"] == "patch-cells"
            assert (out.height, out.width) == (64, 64)

    def test_export_refuses_ungeoreferenced_raster(self, client, project):
        pid = project["id"]
        rng = np.random.default_rng(1)
        data = (rng.random((4, 32, 32)) * 200).astype(np.float32)
        data[:, :, :16] = 0
        ds = _upload(client, pid, _geotiff(data, crs=None))
        assert ds["crs"] is None
        _labels(
            client,
            pid,
            [
                point_label(x, y, "water" if x < 16 else "vegetation", dataset_id=ds["id"])
                for y in range(4, 32, 8)
                for x in range(4, 32, 8)
            ],
        )
        _train(client, pid)
        resp = client.post(f"/projects/{pid}/predict", json={})
        assert resp.status_code == 422
        assert "CRS" in resp.json()["detail"]
        # map layers (no GeoTIFF) still work so the UI can show the field
        field = client.get(f"/projects/{pid}/predict/map", params={"layer": "hard"})
        assert field.status_code == 200, field.text
