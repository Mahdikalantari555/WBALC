"""Phase 4: native-grid scene classification, area math, temporal change, late fusion.

Synthetic data only. The theme: the engine reports areas *with their method*,
refuses to compare grids it cannot prove identical, and never lets a fused map
hide which sensor said what.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio

from app.services.area_service import (
    area_by_class,
    pixel_area_method,
    pixel_areas,
    transitions,
    water_areas,
)

WATER = ["open_water", "emergent_vegetation", "land"]


# ------------------------------------------------------------------ helpers
def scene_bytes(
    *,
    height=32,
    width=32,
    bands=4,
    seed=5,
    crs="EPSG:32631",
    origin=(500000, 4649776),
    resolution=10,
    descriptions=("blue", "green", "red", "nir"),
    split=16,
) -> bytes:
    rng = np.random.default_rng(seed)
    data = np.zeros((bands, height, width), dtype=np.float32)
    # Left half water-like, right half land-like, so classes are separable.
    data[:, :, :split] = np.array([10, 20, 100, 120], dtype=np.float32)[:bands, None, None] + rng.normal(
        0, 2, (bands, height, split)
    )
    data[:, :, split:] = np.array([80, 90, 30, 150], dtype=np.float32)[:bands, None, None] + rng.normal(
        0, 2, (bands, height, width - split)
    )
    buffer = io.BytesIO()
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=bands,
        dtype="float32",
        crs=crs,
        transform=rasterio.transform.from_origin(*origin, resolution, resolution),
    ) as dst:
        dst.write(data)
        if descriptions:
            for index, name in enumerate(descriptions[:bands], start=1):
                dst.set_band_description(index, name)
    return buffer.getvalue()


@pytest.fixture()
def project(client) -> dict:
    resp = client.post("/projects", json={"name": "Temporal", "classes": WATER})
    assert resp.status_code == 201, resp.text
    return resp.json()


def labelled_dataset(client, pid: int) -> int:
    resp = client.post(
        f"/projects/{pid}/upload",
        files={"file": ("dataset.tif", scene_bytes(), "image/tiff")},
        data={"band_names": "blue,green,red,nir"},
    )
    assert resp.status_code == 201, resp.text
    dataset_id = resp.json()["id"]

    def label(x, y, cls):
        return {
            "geometry": {"type": "Point", "coordinates": [x, y]},
            "x": x,
            "y": y,
            "class_name": cls,
            "dataset_id": dataset_id,
        }

    resp = client.post(
        f"/projects/{pid}/labels",
        json={
            "labels": [
                label(4, 4, "open_water"),
                label(20, 4, "open_water"),
                label(4, 20, "land"),
                label(20, 20, "land"),
                label(12, 12, "emergent_vegetation"),
                label(28, 12, "emergent_vegetation"),
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    return dataset_id


def train(client, pid: int) -> dict:
    resp = client.post(
        f"/projects/{pid}/train",
        json={"model_type": "rf", "resolution": "patch", "evaluation_strategy": "random"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def register_scene(client, pid: int, **kwargs) -> int:
    sensor = kwargs.pop("sensor", "Sentinel-2")
    acquired = kwargs.pop("acquired", "2024-01-01T00:00:00Z")
    body = scene_bytes(**kwargs)
    data = {"sensor": sensor, "acquisition_datetime": acquired}
    resp = client.post(
        f"/projects/{pid}/scenes",
        files={"file": ("scene.tif", body, "image/tiff")},
        data=data,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def classify(client, pid: int, scene_id: int, **body):
    return client.post(f"/projects/{pid}/scenes/{scene_id}/classify", json=body)


@pytest.fixture()
def trained(client, project) -> dict:
    labelled_dataset(client, project["id"])
    train(client, project["id"])
    return project


# ------------------------------------------------------------- area geometry
def test_projected_pixel_area_is_det_times_unit_squared():
    from rasterio.crs import CRS

    areas, method = pixel_areas(CRS.from_epsg(32631), [30, 0, 500000, 0, -30, 4649776], 4, 4)
    assert method["kind"] == "projected"
    assert method["supported"] is True
    assert method["pixel_area_m2"] == pytest.approx(900.0)
    assert method["varies_by_row"] is False
    assert areas.shape == (4, 1)


def test_projected_pixel_area_honours_non_metre_units():
    from rasterio.crs import CRS

    # EPSG:2227 is US survey feet; 10 ft pixels are not 100 m².
    crs = CRS.from_epsg(2227)
    assert pixel_area_method(crs)["kind"] == "projected"
    areas, method = pixel_areas(crs, [10, 0, 6000000, 0, -10, 2100000], 2, 2)
    expected = 100 * (1200 / 3937) ** 2
    assert method["pixel_area_m2"] == pytest.approx(expected)
    assert areas[0, 0] == pytest.approx(expected)


def test_projected_pixel_area_refuses_unknown_linear_unit():
    class FakeCRS:
        is_projected = True
        is_geographic = False
        linear_units = "furlong"

        def __str__(self):  # pragma: no cover - debugging aid
            return "furlong-crs"

    method = pixel_area_method(FakeCRS())
    assert method["supported"] is False
    assert "furlong" in method["reason"]
    with pytest.raises(ValueError):
        pixel_areas(FakeCRS(), [1, 0, 0, 0, -1, 0], 2, 2)


def test_geographic_pixel_area_matches_known_ellipsoid_values():
    from rasterio.crs import CRS

    # One degree by one degree at the equator on WGS84 is ~12,308.5 km².
    areas, method = pixel_areas(CRS.from_epsg(4326), [1, 0, 0, 0, -1, 1], 1, 1)
    assert method["kind"] == "geographic"
    assert method["ellipsoid"].startswith("WGS84")
    assert areas[0, 0] / 1e6 == pytest.approx(12308.46, rel=1e-3)

    # And it decreases with latitude: 1° at 60°N is much smaller than at the equator.
    high, _ = pixel_areas(CRS.from_epsg(4326), [1, 0, 0, 0, -1, 61], 1, 1)
    assert high[0, 0] / 1e6 == pytest.approx(6123.14, rel=1e-3)
    assert high[0, 0] < areas[0, 0] / 2


def test_geographic_area_varies_by_row_and_is_reported():
    from rasterio.crs import CRS

    areas, method = pixel_areas(CRS.from_epsg(4326), [0.01, 0, 4.0, 0, -0.01, 52.0], 10, 10)
    assert method["varies_by_row"] is True
    assert areas.shape == (10, 1)
    # Rows step south toward the equator, so each row is slightly larger.
    assert np.all(np.diff(areas[:, 0]) > 0)
    assert method["row_area_min_m2"] < method["row_area_max_m2"]


def test_missing_crs_reports_unsupported_rather_than_guessing():
    method = pixel_area_method(None)
    assert method["supported"] is False
    assert "no CRS" in method["reason"]


# -------------------------------------------------------------- area tables
def test_area_by_class_excludes_invalid_pixels_and_reports_coverage():
    hard = np.array([[0, 0, 1], [1, 0, 0]], dtype=np.int32)
    valid = np.array([[True, True, False], [True, True, False]])
    areas = np.full((2, 1), 100.0)
    summary = area_by_class(hard, valid, ["water", "land"], areas)
    assert summary["valid_pixels"] == 4
    assert summary["invalid_pixels"] == 2
    assert summary["coverage"] == pytest.approx(4 / 6)
    assert summary["per_class"][0]["area_m2"] == pytest.approx(300.0)
    assert summary["per_class"][1]["area_m2"] == pytest.approx(100.0)
    assert summary["valid_area_m2"] == pytest.approx(400.0)


def test_area_by_class_honours_explicit_nodata_sentinel():
    hard = np.array([[0, 65535]], dtype=np.int32)
    valid = np.array([[True, True]])
    summary = area_by_class(hard, valid, ["water"], np.full((1, 1), 4.0), nodata=65535)
    assert summary["valid_pixels"] == 1
    assert summary["per_class"][0]["area_m2"] == pytest.approx(4.0)


def test_water_area_only_counts_declared_water_classes():
    summary = area_by_class(
        np.array([[0, 1, 2]], dtype=np.int32),
        np.ones((1, 3), dtype=bool),
        WATER,
        np.full((1, 1), 10.0),
    )
    water = water_areas(summary, ["open_water"])
    assert water["area_m2"] == pytest.approx(10.0)
    assert water["share_of_valid"] == pytest.approx(1 / 3)


# ---------------------------------------------------------------- transitions
def test_transitions_use_the_jointly_valid_footprint():
    before = np.array([[0, 0], [1, 1]], dtype=np.int32)
    after = np.array([[1, 0], [0, 1]], dtype=np.int32)
    valid_before = np.array([[True, True], [True, False]])
    valid_after = np.array([[True, False], [True, True]])
    result = transitions(
        before, after, valid_before, valid_after, ["water", "land"], np.full((2, 1), 5.0)
    )
    # Only (0,0) and (1,0) are valid in both; both changed class.
    assert result["joint_valid_pixels"] == 2
    assert result["changed_pixels"] == 2
    assert result["changed_area_m2"] == pytest.approx(10.0)
    assert {row["from"] for row in result["changes"]} == {"water", "land"}
    assert result["denominator"] == "pixels valid in both dates"


def test_transitions_reject_mismatched_shapes_instead_of_broadcasting():
    with pytest.raises(ValueError):
        transitions(
            np.zeros((2, 2), dtype=np.int32),
            np.zeros((3, 3), dtype=np.int32),
            np.ones((2, 2), dtype=bool),
            np.ones((3, 3), dtype=bool),
            ["water"],
            np.full((2, 1), 1.0),
        )


# -------------------------------------------------- scene classification API
def test_classification_is_refused_without_a_provable_band_schema(client, project):
    labelled_dataset(client, project["id"])
    train(client, project["id"])
    # Scene with no band descriptions and no names: identity cannot be proven.
    scene_id = register_scene(client, project["id"], descriptions=None)
    resp = classify(client, project["id"], scene_id)
    assert resp.status_code == 422
    assert "cannot be proven" in resp.json()["detail"] or "declares no band" in resp.json()["detail"]


def test_classification_refuses_a_different_sensor_schema(client, project):
    labelled_dataset(client, project["id"])
    train(client, project["id"])
    # Two bands named VV/VH cannot be mistaken for four optical bands, but a
    # four-band stack with different names is the interesting case: same count,
    # different meaning.
    scene_id = register_scene(
        client,
        project["id"],
        seed=9,
        descriptions=("VV", "VH", "blue", "green"),
        sensor="Sentinel-1",
    )
    resp = classify(client, project["id"], scene_id)
    assert resp.status_code == 422
    assert "band schema" in resp.json()["detail"]


def test_classification_records_grid_contract_areas_and_lineage(client, trained):
    pid = trained["id"]
    scene_id = register_scene(client, pid, seed=3)
    resp = classify(client, pid, scene_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()["analysis"]

    assert body["scene_id"] == scene_id
    assert body["grid"]["width"] == 32 and body["grid"]["height"] == 32
    assert body["grid"]["crs"] == "EPSG:32631"
    assert body["contract"]["verified"] is True
    assert set(body["artifacts"]) == {"hard", "probability", "uncertainty"}
    for artifact in body["artifacts"].values():
        assert len(artifact["sha256"]) == 64
        assert artifact["size_bytes"] > 0
    assert body["lineage"]["analysis_digest"]
    assert body["lineage"]["checkpoint_sha256"]
    assert body["lineage"]["scene_content_sha256"]

    areas = body["areas"]
    assert areas["available"] is True
    assert areas["method"]["kind"] == "projected"
    assert areas["method"]["pixel_area_m2"] == pytest.approx(100.0)
    assert areas["valid_pixels"] > 0
    assert areas["coverage"] == pytest.approx(1.0)
    total = sum(entry["area_m2"] for entry in areas["per_class"])
    assert total == pytest.approx(areas["valid_area_m2"])


def test_scene_analysis_is_immutable_and_listed(client, trained):
    pid = trained["id"]
    scene_id = register_scene(client, pid, seed=4)
    first = classify(client, pid, scene_id).json()["analysis"]
    second = classify(client, pid, scene_id).json()["analysis"]
    assert first["id"] != second["id"]
    # A new analysis never rewrites the earlier record.
    assert first["artifacts"] != second["artifacts"]

    listed = client.get(f"/projects/{pid}/scenes/{scene_id}/analyses")
    assert listed.status_code == 200
    ids = [row["id"] for row in listed.json()]
    assert ids == [first["id"], second["id"]]
    reloaded = client.get(f"/projects/{pid}/analyses/{first['id']}").json()
    assert reloaded["artifacts"] == first["artifacts"]
    assert reloaded["lineage"] == first["lineage"]


def test_export_download_is_verified_and_matches_recorded_grid(client, trained):
    pid = trained["id"]
    scene_id = register_scene(client, pid, seed=6)
    analysis = classify(client, pid, scene_id).json()["analysis"]

    resp = client.get(f"/projects/{pid}/analyses/{analysis['id']}/exports/hard")
    assert resp.status_code == 200
    assert resp.headers["X-RSAL-Export-Integrity"] == "verified"
    assert resp.headers["X-RSAL-Export-Sha256"] == analysis["artifacts"]["hard"]["sha256"]

    path = analysis["artifacts"]["hard"]["path"]
    with rasterio.open(path) as src:
        assert list(src.transform)[:6] == pytest.approx(analysis["grid"]["transform"])
        assert src.width == analysis["grid"]["width"]
        assert src.crs.to_string() == analysis["grid"]["crs"]


def test_tampered_export_is_refused_and_the_record_is_untouched(client, trained):
    pid = trained["id"]
    scene_id = register_scene(client, pid, seed=7)
    analysis = classify(client, pid, scene_id).json()["analysis"]
    path = analysis["artifacts"]["hard"]["path"]
    with open(path, "r+b") as handle:
        handle.seek(0)
        handle.write(b"\x00" * 64)

    resp = client.get(f"/projects/{pid}/analyses/{analysis['id']}/exports/hard")
    assert resp.status_code == 409
    assert "integrity" in resp.json()["detail"].lower()
    # The stored record still describes the analysis; nothing was silently repaired.
    kept = client.get(f"/projects/{pid}/analyses/{analysis['id']}").json()
    assert kept["artifacts"]["hard"]["sha256"] == analysis["artifacts"]["hard"]["sha256"]


def test_unknown_export_kind_is_rejected(client, trained):
    pid = trained["id"]
    scene_id = register_scene(client, pid, seed=8)
    analysis = classify(client, pid, scene_id).json()["analysis"]
    resp = client.get(f"/projects/{pid}/analyses/{analysis['id']}/exports/vector")
    assert resp.status_code == 422


# --------------------------------------------------------------- series API
def test_temporal_series_reports_per_date_areas_and_caveats(client, trained):
    pid = trained["id"]
    first = register_scene(client, pid, seed=1, acquired="2024-01-01T00:00:00Z")
    second = register_scene(client, pid, seed=2, acquired="2024-02-01T00:00:00Z")
    classify(client, pid, first)
    classify(client, pid, second)

    resp = client.get(f"/projects/{pid}/temporal/series")
    assert resp.status_code == 200
    body = resp.json()
    assert [date["scene_id"] for date in body["dates"]] == [first, second]
    for date in body["dates"]:
        assert date["valid_area_m2"] > 0
        assert date["coverage"] == pytest.approx(1.0)
        assert sum(entry["area_m2"] for entry in date["per_class"]) == pytest.approx(
            date["valid_area_m2"]
        )
    assert body["alignment"]["mode"] == "native"
    assert body["alignment"]["resampling"] == "none"
    assert body["alignment"]["grids_identical"] is True


def test_temporal_series_requires_a_classified_scene(client, trained):
    resp = client.get(f"/projects/{trained['id']}/temporal/series")
    assert resp.status_code == 409
    assert "classify" in resp.json()["detail"]


def test_temporal_series_flags_differing_grids_instead_of_hiding_them(client, trained):
    pid = trained["id"]
    native = register_scene(client, pid, seed=1, acquired="2024-01-01T00:00:00Z")
    coarse = register_scene(client, pid, seed=2, resolution=20, acquired="2024-02-01T00:00:00Z")
    classify(client, pid, native)
    classify(client, pid, coarse)

    body = client.get(f"/projects/{pid}/temporal/series").json()
    assert body["alignment"]["grids_identical"] is False
    assert any("different grid" in caveat for caveat in body["caveats"])


# -------------------------------------------------------------- compare API
def test_compare_refuses_mismatched_grids_with_structured_detail(client, trained):
    pid = trained["id"]
    native = register_scene(client, pid, seed=1, acquired="2024-01-01T00:00:00Z")
    coarse = register_scene(client, pid, seed=2, resolution=20, acquired="2024-02-01T00:00:00Z")
    classify(client, pid, native)
    classify(client, pid, coarse)

    resp = client.post(
        f"/projects/{pid}/temporal/compare",
        json={"before_scene_id": native, "after_scene_id": coarse},
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "grid_mismatch"
    assert detail["differences"]
    assert any(entry["field"].startswith("transform") for entry in detail["differences"])
    assert detail["resampling_options"] == ["nearest"]


def test_compare_aligns_explicitly_and_records_provenance(client, trained):
    pid = trained["id"]
    native = register_scene(client, pid, seed=1, acquired="2024-01-01T00:00:00Z")
    coarse = register_scene(client, pid, seed=2, resolution=20, acquired="2024-02-01T00:00:00Z")
    classify(client, pid, native)
    classify(client, pid, coarse)

    resp = client.post(
        f"/projects/{pid}/temporal/compare",
        json={
            "before_scene_id": native,
            "after_scene_id": coarse,
            "reference_scene_id": native,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["alignment"]["aligned"] is True
    assert body["alignment"]["method"] == "nearest"
    assert body["alignment"]["target_grid"]["width"] == 32
    assert body["lineage"]["comparison_digest"]
    assert any("nearest-neighbour" in caveat for caveat in body["caveats"])
    # The source analysis record was not modified by the alignment.
    analyses = client.get(f"/projects/{pid}/scenes/{coarse}/analyses").json()
    assert analyses[0]["grid"]["transform"][0] == pytest.approx(20.0)


def test_compare_on_identical_grids_reports_no_resampling(client, trained):
    pid = trained["id"]
    first = register_scene(client, pid, seed=1, acquired="2024-01-01T00:00:00Z")
    second = register_scene(client, pid, seed=2, acquired="2024-02-01T00:00:00Z")
    classify(client, pid, first)
    classify(client, pid, second)

    resp = client.post(
        f"/projects/{pid}/temporal/compare",
        json={"before_scene_id": first, "after_scene_id": second},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["alignment"]["aligned"] is False
    assert body["alignment"]["method"] == "none"
    matrix = np.array(body["transitions"]["matrix"])
    assert matrix.shape == (3, 3)
    assert body["transitions"]["joint_valid_area_m2"] > 0
    assert body["transitions"]["changed_area_ha"] == pytest.approx(
        body["transitions"]["changed_area_m2"] / 10_000
    )
    assert sum(entry["area_m2"] for entry in body["before"]["per_class"]) == pytest.approx(
        body["before"]["valid_area_m2"]
    )


def test_compare_requires_classified_scenes(client, trained):
    pid = trained["id"]
    first = register_scene(client, pid, seed=1)
    resp = client.post(
        f"/projects/{pid}/temporal/compare",
        json={"before_scene_id": first, "after_scene_id": first},
    )
    assert resp.status_code == 409


def test_compare_rejects_a_reference_that_is_not_one_of_the_scenes(client, trained):
    pid = trained["id"]
    first = register_scene(client, pid, seed=1, acquired="2024-01-01T00:00:00Z")
    second = register_scene(client, pid, seed=2, acquired="2024-02-01T00:00:00Z")
    other = register_scene(client, pid, seed=3, resolution=20, acquired="2024-03-01T00:00:00Z")
    for scene in (first, second, other):
        classify(client, pid, scene)
    resp = client.post(
        f"/projects/{pid}/temporal/compare",
        json={
            "before_scene_id": first,
            "after_scene_id": second,
            "reference_scene_id": other,
        },
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------- fusion
def test_fusion_combines_two_sensors_and_keeps_per_source_records(client, trained):
    pid = trained["id"]
    s1 = register_scene(client, pid, seed=1, sensor="Sentinel-1", acquired="2024-01-01T00:00:00Z")
    s2 = register_scene(client, pid, seed=2, sensor="Sentinel-2", acquired="2024-01-02T00:00:00Z")
    a1 = classify(client, pid, s1).json()["analysis"]["id"]
    a2 = classify(client, pid, s2).json()["analysis"]["id"]

    resp = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "weighted_probability",
            "target_scene_id": s1,
            "analysis_ids": [a1, a2],
            "weights": {"Sentinel-1": 0.7, "Sentinel-2": 0.3},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["rule"] == "weighted_probability"
    assert body["weights"] == {"Sentinel-1": 0.7, "Sentinel-2": 0.3}
    assert [source["analysis_id"] for source in body["sources"]] == [a1, a2]
    assert all(source["analysis_digest"] for source in body["sources"])
    assert body["target_grid"]["width"] == 32
    assert body["lineage"]["fusion_digest"]
    assert body["lineage"]["fusion_kind"] == "late"
    assert body["areas"]["per_class"]
    assert body["agreement"]["sources"] == 2
    assert body["agreement"]["fused_valid_pixels"] > 0
    assert body["artifacts"]["hard"]["sha256"]

    listed = client.get(f"/projects/{pid}/fusion")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_fusion_rejects_raw_band_early_fusion(client, trained):
    pid = trained["id"]
    scene = register_scene(client, pid, seed=1, sensor="Sentinel-1")
    analysis = classify(client, pid, scene).json()["analysis"]["id"]
    resp = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "raw_band_fusion",
            "target_scene_id": scene,
            "analysis_ids": [analysis, analysis],
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "early_fusion_rejected"
    assert "weighted_probability" in detail["supported_rules"]


def test_fusion_needs_at_least_two_distinct_sources(client, trained):
    pid = trained["id"]
    scene = register_scene(client, pid, seed=1, sensor="Sentinel-1")
    analysis = classify(client, pid, scene).json()["analysis"]["id"]
    single = client.post(
        f"/projects/{pid}/fusion",
        json={"rule": "weighted_probability", "target_scene_id": scene, "analysis_ids": [analysis]},
    )
    assert single.status_code == 422
    duplicate = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "weighted_probability",
            "target_scene_id": scene,
            "analysis_ids": [analysis, analysis],
        },
    )
    assert duplicate.status_code == 422


def test_fusion_alignment_is_explicit_and_recorded(client, trained):
    pid = trained["id"]
    native = register_scene(client, pid, seed=1, sensor="Sentinel-1", acquired="2024-01-01T00:00:00Z")
    coarse = register_scene(
        client, pid, seed=2, sensor="Sentinel-2", resolution=20, acquired="2024-01-02T00:00:00Z"
    )
    a1 = classify(client, pid, native).json()["analysis"]["id"]
    a2 = classify(client, pid, coarse).json()["analysis"]["id"]

    resp = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "weighted_probability",
            "target_scene_id": native,
            "analysis_ids": [a1, a2],
            "weights": {"Sentinel-1": 0.5, "Sentinel-2": 0.5},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    aligned = [source for source in body["sources"] if source["grid_aligned"]]
    assert [source["analysis_id"] for source in aligned] == [a2]
    assert body["alignment"]["resampling"] == "nearest"
    assert body["alignment"]["aligned_sources"] == [a2]


def test_fusion_priority_rule_prefers_the_first_valid_source(client, trained):
    pid = trained["id"]
    s1 = register_scene(client, pid, seed=1, sensor="Sentinel-1", acquired="2024-01-01T00:00:00Z")
    s2 = register_scene(client, pid, seed=2, sensor="Sentinel-2", acquired="2024-01-02T00:00:00Z")
    a1 = classify(client, pid, s1).json()["analysis"]["id"]
    a2 = classify(client, pid, s2).json()["analysis"]["id"]

    resp = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "priority",
            "target_scene_id": s1,
            "analysis_ids": [a1, a2],
            "priority": [a2, a1],
        },
    )
    assert resp.status_code == 201, resp.text
    assert "priority order" in resp.json()["lineage"]["missing_semantics"]

    bad = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "priority",
            "target_scene_id": s1,
            "analysis_ids": [a1, a2],
            "priority": [a1],
        },
    )
    assert bad.status_code == 422


def test_fusion_rejects_negative_weights(client, trained):
    pid = trained["id"]
    s1 = register_scene(client, pid, seed=1, sensor="Sentinel-1", acquired="2024-01-01T00:00:00Z")
    s2 = register_scene(client, pid, seed=2, sensor="Sentinel-2", acquired="2024-01-02T00:00:00Z")
    a1 = classify(client, pid, s1).json()["analysis"]["id"]
    a2 = classify(client, pid, s2).json()["analysis"]["id"]
    resp = client.post(
        f"/projects/{pid}/fusion",
        json={
            "rule": "weighted_probability",
            "target_scene_id": s1,
            "analysis_ids": [a1, a2],
            "weights": {"Sentinel-1": -1.0},
        },
    )
    assert resp.status_code == 422
