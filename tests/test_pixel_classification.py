"""Regression coverage for supervised source-pixel classification."""
from __future__ import annotations

import io
import numpy as np
import rasterio
from affine import Affine

from .conftest import point_label


def test_pixel_rf_training_predict_and_export_preserve_reference_grid(client, project, dataset):
    pid = project["id"]
    labels = [point_label(col * 8 + 4, row * 8 + 4, "water" if col < 4 else "vegetation")
              for row in range(8) for col in range(8)]
    assert client.post(f"/projects/{pid}/labels", json={"labels": labels}).status_code == 201
    trained = client.post(f"/projects/{pid}/train", json={
        "model_type": "rf", "resolution": "pixel", "params": {"n_estimators": 20}
    })
    assert trained.status_code == 201, trained.text
    assert trained.json()["n_samples"] == 64
    prediction = client.post(f"/projects/{pid}/predict", json={})
    assert prediction.status_code == 200, prediction.text
    body = prediction.json()
    assert body["grid_shape"] == [64, 64]
    hard = np.asarray(body["hard_map"])
    assert hard.shape == (64, 64)
    assert (hard[:, :32] == 0).all()
    assert (hard[:, 32:] == 1).all()
    source = client.get(f"/projects/{pid}/dataset/{dataset['id']}/file")
    with rasterio.open(io.BytesIO(source.content)) as ref:
        ref_transform, ref_crs, ref_bounds, ref_shape = ref.transform, ref.crs, ref.bounds, (ref.height, ref.width)
    response = client.get(f"/projects/{pid}/download/hard")
    assert response.status_code == 200
    with rasterio.open(io.BytesIO(response.content)) as out:
        assert (out.height, out.width) == ref_shape
        assert out.crs == ref_crs
        assert out.transform == ref_transform
        assert out.bounds == ref_bounds
        assert set(np.unique(out.read(1))) <= {0, 1}
    region = {"x0": 2, "y0": 3, "x1": 17, "y1": 21}
    predicted_region = client.post(f"/projects/{pid}/predict", json={"region": region})
    assert predicted_region.status_code == 200, predicted_region.text
    regional_file = client.get(f"/projects/{pid}/download/hard")
    with rasterio.open(io.BytesIO(regional_file.content)) as out:
        assert (out.width, out.height) == (15, 18)
        assert out.transform == ref_transform * Affine.translation(region["x0"], region["y0"])


def test_pixel_feature_checkpoint_contract(client, project, dataset):
    pid = project["id"]
    labels = [point_label(col * 8 + 4, row * 8 + 4, "water" if col < 4 else "vegetation")
              for row in range(2) for col in range(8)]
    client.post(f"/projects/{pid}/labels", json={"labels": labels})
    response = client.post(f"/projects/{pid}/train", json={"resolution": "pixel", "params": {"n_estimators": 5}})
    assert response.status_code == 201, response.text
    import joblib
    assert joblib.load(response.json()["checkpoint"])["resolution"] == "pixel"


def test_pixel_lightgbm_training_predicts_source_grid(client, project, dataset):
    labels = [point_label(col * 8 + 4, row * 8 + 4, "water" if col < 4 else "vegetation")
              for row in range(2) for col in range(8)]
    client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
    trained = client.post(f"/projects/{project['id']}/train", json={
        "model_type": "lightgbm", "resolution": "pixel",
        "params": {"n_estimators": 5, "min_child_samples": 1},
    })
    assert trained.status_code == 201, trained.text
    pred = client.post(f"/projects/{project['id']}/predict", json={})
    assert pred.status_code == 200, pred.text
    assert pred.json()["grid_shape"] == [64, 64]


def test_spatial_evaluation_uses_group_holdout_and_reports_iou():
    from app.services.training_service import train_model
    X = np.asarray([[float(i % 2), float(i // 2)] for i in range(80)])
    y = [i % 2 for i in range(80)]
    groups = np.repeat(np.arange(8), 10)
    _, metrics, evaluation = train_model(
        X, y, ["a", "b"], "rf", {"n_estimators": 10}, 0.25, 7,
        evaluation_strategy="spatial", groups=groups,
    )
    assert evaluation == "spatial_holdout"
    assert metrics["n_test"] > 0
    assert metrics["held_out_groups"] >= 1
    assert set(metrics["per_class"]["a"]) >= {"precision", "recall", "f1", "iou", "support"}


def test_pixel_mode_partial_edges_nodata_non_square_pixels_and_crs(client, project):
    from affine import Affine
    from rasterio.io import MemoryFile
    height, width = 7, 11
    data = np.zeros((2, height, width), dtype=np.float32)
    data[:, :, :5] = np.array([1, 10], dtype=np.float32)[:, None, None]
    data[:, :, 5:] = np.array([20, 2], dtype=np.float32)[:, None, None]
    data[:, 3, 4] = -9999
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", height=height, width=width, count=2, dtype="float32",
                      crs="EPSG:4326", transform=Affine(0.01, 0.002, 12, 0.003, -0.02, 55), nodata=-9999) as ds:
            ds.write(data)
        payload = mem.read()
    upload = client.post(f"/projects/{project['id']}/upload", files={"file": ("edge.tif", payload, "image/tiff")})
    assert upload.status_code == 201, upload.text
    dsid = upload.json()["id"]
    labels = [point_label(col, row, "water" if col < 5 else "vegetation", dataset_id=dsid, sample_resolution="pixel")
              for row in (0, 2, 5, 6) for col in (1, 3, 7, 9)]
    assert client.post(f"/projects/{project['id']}/labels", json={"labels": labels}).status_code == 201
    train = client.post(f"/projects/{project['id']}/train", json={"resolution": "pixel", "params": {"n_estimators": 10}})
    assert train.status_code == 201, train.text
    pred = client.post(f"/projects/{project['id']}/predict", json={"dataset_id": dsid})
    assert pred.status_code == 200, pred.text
    assert pred.json()["grid_shape"] == [height, width]
    exported = client.get(f"/projects/{project['id']}/download/hard")
    with rasterio.open(io.BytesIO(exported.content)) as out, MemoryFile(payload) as refmem:
        with refmem.open() as ref:
            assert (out.width, out.height) == (ref.width, ref.height)
            assert out.crs == ref.crs
            assert out.transform == ref.transform
            assert out.bounds == ref.bounds
        assert out.nodata == 65535
        arr = out.read(1)
        assert arr[3, 4] == 65535
        assert set(np.unique(arr)) <= {0, 1, 65535}
    probability_file = client.get(f"/projects/{project['id']}/download/probability")
    with rasterio.open(io.BytesIO(probability_file.content)) as out:
        assert out.nodata == -9999.0
        assert np.all(out.read()[:, 3, 4] == -9999.0)
        valid_prob = out.read()[:, 0, 0]
        assert np.isclose(valid_prob.sum(), 1.0)
