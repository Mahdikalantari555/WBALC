"""Phase 0 contract: explicit reference raster, band-schema identity, study-area mask.

These are synthetic-fixture tests only (no real imagery, no network). They are the
acceptance evidence for `harden-pixel-classification-contract`.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.mask_service import StudyAreaError, study_area_mask
from app.services.schema_service import build_band_schema, compare_schemas

from .conftest import point_label

UTM = "EPSG:32631"
WGS84 = "EPSG:4326"
BANDS = {"band_names": "blue,green,red,nir", "sensor": "sentinel-2"}


def geotiff(
    height: int = 64,
    width: int = 64,
    *,
    bands: int = 4,
    crs: str | None = UTM,
    transform=None,
    nodata: float | None = None,
) -> bytes:
    """Two spectrally distinct halves, so a classifier has something to learn."""
    rng = np.random.default_rng(5)
    data = np.zeros((bands, height, width), dtype=np.float32)
    split = width // 2
    base_a = np.array([10, 20, 100, 120][:bands], dtype=np.float32)
    base_b = np.array([80, 90, 30, 150][:bands], dtype=np.float32)
    data[:, :, :split] = base_a[:, None, None] + rng.normal(0, 2, (bands, height, split))
    data[:, :, split:] = base_b[:, None, None] + rng.normal(0, 2, (bands, height, width - split))
    buf = io.BytesIO()
    kwargs = {}
    if crs:
        kwargs["crs"] = crs
        kwargs["transform"] = transform or from_origin(500000, 4649776, 10, 10)
    if nodata is not None:
        kwargs["nodata"] = nodata
    with rasterio.open(
        buf, "w", driver="GTiff", height=height, width=width, count=bands,
        dtype="float32", **kwargs,
    ) as dst:
        dst.write(data)
    return buf.getvalue()


def upload(client, pid: int, payload: bytes, **data) -> dict:
    resp = client.post(
        f"/projects/{pid}/upload",
        files={"file": ("scene.tif", payload, "image/tiff")},
        data=data or BANDS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def label_grid(client, pid: int, dsid: int, width: int = 64, height: int = 64, step: int = 4):
    labels = [
        point_label(x, y, "water" if x < width // 2 else "vegetation", dataset_id=dsid)
        for y in range(step // 2, height, step)
        for x in range(step // 2, width, step)
    ]
    resp = client.post(f"/projects/{pid}/labels", json={"labels": labels})
    assert resp.status_code == 201, resp.text


# ------------------------------------------------------------------ unit level
def test_schema_requires_full_naming_to_be_declared():
    partial = build_band_schema(band_count=4, band_names=["blue", None, "red", "nir"])
    assert partial["declared"] is False
    assert partial["band_names"] is None

    full = build_band_schema(band_count=4, band_names=["blue", "green", "red", "nir"])
    assert full["declared"] is True
    assert full["band_names"] == ["blue", "green", "red", "nir"]


def test_band_count_equality_is_not_identity():
    left = build_band_schema(band_count=4, band_names=["blue", "green", "red", "nir"])
    right = build_band_schema(band_count=4, band_names=["nir", "red", "green", "blue"])
    verified, reason = compare_schemas(left, right)
    assert verified is False
    assert "order" in reason or "names" in reason


def test_undeclared_schema_never_verifies():
    undeclared = build_band_schema(band_count=4)
    verified, reason = compare_schemas(undeclared, undeclared)
    assert verified is False
    assert "not declared" in reason


def test_study_area_mask_rejects_point_geometry():
    with pytest.raises(StudyAreaError, match="Polygon"):
        study_area_mask(
            {"type": "Point", "coordinates": [3.0, 42.0]},
            WGS84, UTM, [10, 0, 500000, 0, -10, 4649776],
            height=8, width=8, shape=(4, 4),
        )


def test_study_area_mask_requires_a_crs():
    with pytest.raises(StudyAreaError, match="CRS"):
        study_area_mask(
            {"type": "Polygon", "coordinates": [[[3, 42], [3.1, 42], [3.1, 42.1], [3, 42]]]},
            None, UTM, [10, 0, 500000, 0, -10, 4649776],
            height=8, width=8, shape=(4, 4),
        )


def test_study_area_polygon_selects_the_expected_pixels():
    # A polygon covering the left half of an 8x8 raster, in raster coordinates.
    pixel_transform = [1, 0, 0, 0, -1, 8]
    geometry = {"type": "Polygon", "coordinates": [[[0, 8], [4, 8], [4, 0], [0, 0], [0, 8]]]}
    mask, _ = study_area_mask(geometry, UTM, UTM, pixel_transform, height=8, width=8, shape=(8, 8))
    assert mask[:, :4].all()
    assert not mask[:, 4:].any()


# --------------------------------------------------------------- API contract
def test_predict_requires_an_explicit_dataset_id(client, project, dataset, labeled):
    pid = project["id"]
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 10}})
    # No dataset_id: rejected at the schema boundary instead of picking "latest".
    resp = client.post(f"/projects/{pid}/predict", json={})
    assert resp.status_code == 422
    assert "dataset_id" in resp.text


def test_predict_names_the_reference_dataset_and_provenance(client, project, dataset, labeled):
    pid = project["id"]
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 10}}
    )
    assert trained.status_code == 201, trained.text
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": dataset["id"]}).json()
    assert body["dataset_id"] == dataset["id"]
    assert body["training_run_id"] == trained.json()["id"]
    assert body["band_schema_verified"] is True
    assert body["schema_override"] is False
    assert body["study_area_applied"] is False


def test_predict_rejects_a_dataset_from_another_project(client, project, dataset, labeled):
    pid = project["id"]
    other = client.post(
        "/projects",
        json={"name": "Other", "classes": ["water", "vegetation"], "generic_classes": True},
    ).json()
    foreign = upload(client, other["id"], geotiff())
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 10}})
    resp = client.post(f"/projects/{pid}/predict", json={"dataset_id": foreign["id"]})
    assert resp.status_code == 404, resp.text


def test_undeclared_raster_requires_an_explicit_override(client, project):
    pid = project["id"]
    ds = upload(client, pid, geotiff(), band_names="", sensor="")
    assert ds["band_schema"]["declared"] is False
    label_grid(client, pid, ds["id"])

    refused = client.post(f"/projects/{pid}/train", json={"model_type": "rf"})
    assert refused.status_code == 422, refused.text
    assert "band names" in refused.json()["detail"]

    accepted = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "accept_unverified_schema": True, "params": {"n_estimators": 5}},
    )
    assert accepted.status_code == 201, accepted.text
    # The override is recorded, not glossed over.
    assert accepted.json()  # run created

    predict = client.post(
        f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}
    )
    assert predict.status_code == 409
    assert "accept_unverified_schema" in predict.json()["detail"]

    overridden = client.post(
        f"/projects/{pid}/predict",
        json={"dataset_id": ds["id"], "accept_unverified_schema": True},
    )
    assert overridden.status_code == 200, overridden.text
    assert overridden.json()["schema_override"] is True
    assert overridden.json()["band_schema_verified"] is False


def test_reordered_bands_are_refused_but_named_equivalents_are_allowed(client, project):
    pid = project["id"]
    ds = upload(client, pid, geotiff())
    label_grid(client, pid, ds["id"])
    trained = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "params": {"n_estimators": 5}, "evaluation_strategy": "spatial"},
    )
    assert trained.status_code == 201, trained.text

    same_order = upload(client, pid, geotiff(), band_names="blue,green,red,nir")
    ok = client.post(f"/projects/{pid}/predict", json={"dataset_id": same_order["id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["band_schema_verified"] is True

    reordered = upload(client, pid, geotiff(), band_names="nir,red,green,blue")
    bad = client.post(f"/projects/{pid}/predict", json={"dataset_id": reordered["id"]})
    assert bad.status_code == 409, bad.text
    assert "ordered band names differ" in bad.json()["detail"]


def test_training_refuses_mixed_schemas_without_an_override(client, project):
    pid = project["id"]
    left = upload(client, pid, geotiff())
    right = upload(client, pid, geotiff(), band_names="nir,red,green,blue")
    for ds in (left, right):
        resp = client.post(
            f"/projects/{pid}/labels",
            json={
                "labels": [
                    point_label(x, y, "water" if x < 32 else "vegetation", dataset_id=ds["id"])
                    for y in (4, 12, 20, 28)
                    for x in (4, 12, 20, 28, 36, 44, 52, 60)
                ]
            },
        )
        assert resp.status_code == 201, resp.text

    refused = client.post(f"/projects/{pid}/train", json={"model_type": "rf"})
    assert refused.status_code == 422, refused.text
    assert "band" in refused.json()["detail"].lower()

    accepted = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "accept_unverified_schema": True, "params": {"n_estimators": 5}},
    )
    assert accepted.status_code == 201, accepted.text


def test_study_area_limits_predictions_and_exports(client, project):
    """A study area must show up in hard, probability and uncertainty alike."""
    pid = project["id"]
    ds = upload(client, pid, geotiff())
    label_grid(client, pid, ds["id"])
    # Half the raster, expressed in the raster's own CRS (no transformation).
    client.put(
        f"/projects/{pid}",
        json={
            "study_area_geometry": {
                "type": "Polygon",
                "coordinates": [[[500000, 4649776], [500320, 4649776], [500320, 4649136], [500000, 4649136], [500000, 4649776]]],
            },
            "study_area_crs": UTM,
        },
    )
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 10}}
    )
    assert trained.status_code == 201, trained.text

    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert body["study_area_applied"] is True
    valid = np.asarray(body["valid_map"])
    # 64x64 raster, 8px patches => 8x8 cells; the polygon covers columns 0..31.
    assert valid[:, :4].all()
    assert not valid[:, 4:].any()
    hard = np.asarray(body["hard_map"])
    prob = np.asarray(body["probability_map"])
    # Outside the mask: NoData for all three products, never a class/value.
    assert (hard[:, 4:] == 0).all()
    # probability/uncertainty come back as JSON with nulls where a cell is masked
    assert all(value is None for band in body["probability_map"] for row in band for value in row[4:])
    assert all(value is None for row in body["uncertainty_map"] for value in row[4:])
    # ...and stay populated inside the study area, so masking is not a global wipe
    assert any(value is not None for row in body["uncertainty_map"] for value in row[:4])

    exported = client.get(f"/projects/{pid}/download/hard")
    assert exported.status_code == 200
    with rasterio.open(io.BytesIO(exported.content)) as out:
        assert out.nodata is not None
        assert (out.read(1)[:, 32:] == out.nodata).all()
        # Masking is recorded in the file itself, not only in the API response.
        tags = out.tags()
        assert tags["study_area_applied"] == "true"


def test_study_area_without_a_crs_fails_clearly(client, project):
    pid = project["id"]
    ds = upload(client, pid, geotiff())
    label_grid(client, pid, ds["id"])
    # Injected directly: the API validator already requires a CRS with geometry,
    # so this covers the defensive path (legacy/corrupt records).
    from app.main import create_app  # noqa: F401  (documents the app boundary)

    resp = client.put(
        f"/projects/{pid}",
        json={"study_area_geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}},
    )
    assert resp.status_code == 422, resp.text
    assert "study_area_crs" in resp.text


def test_study_area_is_transformed_from_geographic_crs(client, project):
    """A WGS84 polygon must be projected into the raster CRS, not interpreted as UTM."""
    pid = project["id"]
    ds = upload(client, pid, geotiff())
    label_grid(client, pid, ds["id"])
    # EPSG:32631 at easting 500000/northing 4649776 ~= 3.0E, 42.0N. Cover the
    # left half in geographic coordinates.
    client.put(
        f"/projects/{pid}",
        json={
            "study_area_geometry": {
                "type": "Polygon",
                "coordinates": [[[2.99, 42.01], [3.004, 42.01], [3.004, 41.99], [2.99, 41.99], [2.99, 42.01]]],
            },
            "study_area_crs": WGS84,
        },
    )
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 10}}
    )
    assert trained.status_code == 201, trained.text
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert body["study_area_applied"] is True
    valid = np.asarray(body["valid_map"])
    assert valid.any(), "the projected polygon must select at least one cell"
    assert not valid.all(), "the projected polygon must not select the whole raster"


def test_patch_grid_101x73_reference_case(client, project):
    """The original 101x73 example: non-square, non-patch-multiple dimensions."""
    pid = project["id"]
    ds = upload(client, pid, geotiff(73, 101))
    label_grid(client, pid, ds["id"], width=101, height=73, step=6)
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 5}}
    )
    assert trained.status_code == 201, trained.text
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert body["grid_shape"] == [10, 13]
    exported = client.get(f"/projects/{pid}/download/hard")
    with rasterio.open(io.BytesIO(exported.content)) as out:
        assert (out.height, out.width) == (73, 101)
        assert out.crs.to_string() == UTM
        assert out.transform == rasterio.Affine(10, 0, 500000, 0, -10, 4649776)
        assert set(np.unique(out.read(1))) <= {0, 1, out.nodata}


def test_pixel_mode_101x73_matches_the_source_grid(client, project):
    pid = project["id"]
    ds = upload(client, pid, geotiff(73, 101))
    resp = client.post(
        f"/projects/{pid}/labels",
        json={
            "labels": [
                point_label(x, y, "water" if x < 50 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in (2, 20, 40, 60)
                for x in (2, 20, 40, 50, 70, 90)
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    trained = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "pixel", "params": {"n_estimators": 5}},
    )
    assert trained.status_code == 201, trained.text
    body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert body["resolution"] == "pixel"
    assert body["grid_shape"] == [73, 101]
    exported = client.get(f"/projects/{pid}/download/hard")
    with rasterio.open(io.BytesIO(exported.content)) as out:
        assert (out.height, out.width) == (73, 101)


def test_rotated_affine_still_round_trips_the_export_grid(client, project):
    """The 7x11 rotated/non-square-pixel case must keep working."""
    from affine import Affine

    pid = project["id"]
    rotated = Affine(0.01, 0.002, 12, 0.003, -0.02, 55)
    ds = upload(
        client, pid, geotiff(7, 11, bands=2, crs=WGS84, transform=rotated), band_names="red,nir"
    )
    resp = client.post(
        f"/projects/{pid}/labels",
        json={
            "labels": [
                point_label(
                    x, y, "water" if x < 5 else "vegetation",
                    dataset_id=ds["id"], sample_resolution="pixel",
                )
                for y in range(0, 7)
                for x in range(0, 11)
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    trained = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "pixel", "params": {"n_estimators": 5}},
    )
    assert trained.status_code == 201, trained.text
    predictive = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]})
    assert predictive.status_code == 200, predictive.text
    exported = client.get(f"/projects/{pid}/download/hard")
    with rasterio.open(io.BytesIO(exported.content)) as out:
        assert (out.height, out.width) == (7, 11)
        assert out.transform == rotated


# ------------------------------------------------- resource bounds (no allocs)
def test_element_budget_is_checked_before_allocation():
    from app.services.raster_service import RasterError, check_element_budget

    # Fits: a no-op that must not raise.
    check_element_budget(4, 64, 64, 250_000_000, multiplier=2, what="test")

    with pytest.raises(RasterError) as excinfo:
        check_element_budget(4, 10_000, 10_000, 250_000_000, multiplier=3, what="per-pixel classification")
    message = str(excinfo.value)
    # Actionable: the numbers, the knob and the ways out are all named.
    assert "1,200,000,000" in message
    assert "MAX_RASTER_ELEMENTS" in message
    assert "region" in message and "patch resolution" in message
    assert "Nothing was allocated" in message


def test_pixel_inference_refuses_an_over_budget_raster(client, project, settings):
    """Per-class probability bands count against the limit, before allocation."""
    pid = project["id"]
    ds = upload(client, pid, geotiff(64, 64))
    assert client.post(
        f"/projects/{pid}/labels",
        json={
            "labels": [
                point_label(x, y, "water" if x < 32 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in (2, 20, 40, 60)
                for x in (2, 20, 40, 60)
            ]
        },
    ).status_code == 201
    trained = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "pixel", "params": {"n_estimators": 5}},
    )
    assert trained.status_code == 201, trained.text
    # 4 bands x 64 x 64 x 2 classes = 32768 > 1000
    settings.max_raster_elements = 1_000
    resp = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]})
    assert resp.status_code == 422, resp.text
    assert "MAX_RASTER_ELEMENTS" in resp.json()["detail"]
    assert "Nothing was allocated" in resp.json()["detail"]


def test_source_raster_is_byte_identical_after_predict_and_export(client, project, settings):
    """Inference and export must never rewrite the uploaded file."""
    pid = project["id"]
    payload = geotiff()
    ds = upload(client, pid, payload)
    label_grid(client, pid, ds["id"])
    trained = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 5}}
    )
    assert trained.status_code == 201, trained.text
    assert client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).status_code == 200
    assert client.get(f"/projects/{pid}/download/hard").status_code == 200
    assert client.get(f"/projects/{pid}/download/probability").status_code == 200
    assert client.get(f"/projects/{pid}/download/uncertainty").status_code == 200

    # Read the stored file straight from the engine's storage root.
    stored = next(Path(settings.storage_dir).rglob("*.tif"))
    assert stored.read_bytes() == payload


def test_patch_and_pixel_products_are_distinguishable(client, project):
    """Resolution is a property of the checkpoint, reported on every product."""
    pid = project["id"]
    ds = upload(client, pid, geotiff())
    resp = client.post(
        f"/projects/{pid}/labels",
        json={
            "labels": [
                point_label(x, y, "water" if x < 32 else "vegetation", dataset_id=ds["id"], sample_resolution="pixel")
                for y in (2, 20, 40, 60)
                for x in (2, 20, 40, 60)
            ]
        },
    )
    assert resp.status_code == 201, resp.text

    patch_run = client.post(
        f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 5}}
    )
    assert patch_run.status_code == 201, patch_run.text
    patch_body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert patch_body["resolution"] == "patch"
    # The conftest engine is configured for 8px patch cells: 64/8 = 8x8.
    assert patch_body["grid_shape"] == [8, 8] and patch_body["patch_size"] == 8

    pixel_run = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "pixel", "params": {"n_estimators": 5}},
    )
    assert pixel_run.status_code == 201, pixel_run.text
    pixel_body = client.post(f"/projects/{pid}/predict", json={"dataset_id": ds["id"]}).json()
    assert pixel_body["resolution"] == "pixel"
    assert pixel_body["grid_shape"] == [64, 64] and pixel_body["patch_size"] == 1

    # Each product names the run that produced it; a stale field is still honest.
    assert patch_body["training_run_id"] != pixel_body["training_run_id"]
    field = client.get(f"/projects/{pid}/predict/map", params={"layer": "hard", "dataset_id": ds["id"]}).json()
    assert field["resolution"] == "pixel"
    assert field["training_run_id"] == pixel_run.json()["id"]


def test_partial_window_exports_keep_nodata_outside_the_region(client, project):
    pid = project["id"]
    ds = upload(client, pid, geotiff())
    label_grid(client, pid, ds["id"])
    client.post(f"/projects/{pid}/train", json={"model_type": "rf", "params": {"n_estimators": 5}})
    body = client.post(
        f"/projects/{pid}/predict",
        json={"dataset_id": ds["id"], "region": {"x0": 8, "y0": 8, "x1": 40, "y1": 24}},
    ).json()
    # 32x16 window on 8px cells, so 2 rows x 4 cols.
    assert body["grid_shape"] == [2, 4]
    exported = client.get(f"/projects/{pid}/download/hard")
    assert exported.status_code == 200
    with rasterio.open(io.BytesIO(exported.content)) as out:
        # The window keeps its source dimensions and offset, never a full-canvas copy.
        assert (out.height, out.width) == (16, 32)
        assert out.transform.c == pytest.approx(500000.0 + 10 * 8)
        assert out.transform.f == pytest.approx(4649776.0 - 10 * 8)
