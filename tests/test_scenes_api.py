"""WBALC multi-temporal scene foundation API and persistence scenarios."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.raster_service import compare_grid_metadata, extract_scene_metadata


def geotiff(*, width=8, height=6, crs="EPSG:32631", transform=None, nodata=None, mask=False, dtype="uint16"):
    buffer = io.BytesIO()
    transform = transform or from_origin(500000, 4649776, 10, 10)
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=2,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        data = np.arange(2 * height * width, dtype=dtype).reshape(2, height, width)
        dst.write(data)
        dst.set_band_description(1, "B04")
        dst.set_band_description(2, "B08")
        if mask:
            valid = np.full((height, width), 255, dtype=np.uint8)
            valid[0, 0] = 0
            dst.write_mask(valid)
    return buffer.getvalue()


def upload(client, project_id, content, **metadata):
    return client.post(
        f"/projects/{project_id}/scenes",
        files={"file": (metadata.pop("filename", "scene.tif"), content, "image/tiff")},
        data=metadata,
    )


class TestSceneFoundation:
    def test_project_study_area_validation_and_persistence(self, client):
        bad = client.post("/projects", json={
            "name": "bad geometry",
            "study_area_geometry": {"type": "Point", "coordinates": [1, 2]},
        })
        assert bad.status_code == 422
        valid = client.post("/projects", json={
            "name": "estuary",
            "study_area_crs": "EPSG:4326",
            "study_area_geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        })
        assert valid.status_code == 201, valid.text
        read = client.get(f"/projects/{valid.json()['id']}").json()
        assert read["study_area_crs"] == "EPSG:4326"
        assert read["study_area_geometry"]["type"] == "Polygon"

        collection = client.post("/projects", json={
            "name": "multi-feature study",
            "study_area_crs": "EPSG:4326",
            "study_area_geometry": {"type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {}, "geometry": {
                    "type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
                {"type": "Feature", "properties": {}, "geometry": {
                    "type": "Polygon", "coordinates": [[[2, 0], [3, 0], [3, 1], [2, 0]]]}},
            ]},
        })
        assert collection.status_code == 201, collection.text
        assert collection.json()["study_area_geometry"]["type"] == "MultiPolygon"
        assert len(collection.json()["study_area_geometry"]["coordinates"]) == 2

        feature = client.post("/projects", json={
            "name": "feature study",
            "study_area_crs": "EPSG:4326",
            "study_area_geometry": {"type": "Feature", "properties": {}, "geometry": {
                "type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
        })
        assert feature.status_code == 201, feature.text
        assert feature.json()["study_area_geometry"]["type"] == "Polygon"

        multi = client.post("/projects", json={
            "name": "multi geometry study",
            "study_area_crs": "EPSG:4326",
            "study_area_geometry": {"type": "MultiPolygon", "coordinates": [
                [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                [[[2, 0], [3, 0], [3, 1], [2, 0]]],
            ]},
        })
        assert multi.status_code == 201, multi.text
        assert multi.json()["study_area_geometry"]["type"] == "MultiPolygon"

    def test_project_defaults_and_binary_semantics(self, client):
        created = client.post("/projects", json={"name": "wetland"})
        assert created.status_code == 201, created.text
        project = created.json()
        assert project["classes"] == ["open_water", "emergent_vegetation", "land"]
        assert project["classification_config"] == {
            "label_aliases": {},
            "internal_classes": ["open_water", "emergent_vegetation", "land"],
            "binary_output_interpretation": "water_vs_non_water",
        }
        updated = client.put(
            f"/projects/{project['id']}",
            json={"classification_config": {
                "internal_classes": ["open_water", "emergent_vegetation", "land"],
                "binary_output_interpretation": "open_water_vs_other",
            }},
        )
        assert updated.json()["classification_config"]["binary_output_interpretation"] == "open_water_vs_other"
        invalid = client.put(
            f"/projects/{project['id']}", json={"classification_config": {"internal_classes": ["water"]}}
        )
        assert invalid.status_code == 422

    def test_register_sentinel_1_and_2_independently_and_order_temporally(self, client, project):
        first = upload(
            client, project["id"], geotiff(nodata=0, mask=True), sensor="Sentinel-1",
            acquisition_datetime="2024-04-01T10:30:00Z", platform="Sentinel-1A",
            polarization="VV,VH", acquisition_mode="IW", orbit_direction="ascending", relative_orbit="54",
            product_type="GRD", product_level="GRD", filename="s1.tif",
        )
        assert first.status_code == 201, first.text
        a = first.json()
        assert a["sensor"] == "Sentinel-1"
        assert a["polarization"] == ["VH", "VV"]
        assert a["acquisition_mode"] == "IW" and a["relative_orbit"] == 54
        assert a["band_count"] == 2 and a["band_names"] == ["B04", "B08"]
        assert a["band_dtypes"] == ["uint16", "uint16"]
        assert a["nodata_values"] == [0.0, 0.0]
        assert a["has_validity_mask"] is True
        assert a["crs"] == "EPSG:32631" and a["resolution_x"] == pytest.approx(10)
        assert a["width"] == 8 and a["height"] == 6
        assert a["source_filename"] == "s1.tif" and a["size_bytes"] > 0
        assert a["registered_at"].endswith("Z") and a["uploaded_at"].endswith("Z")
        assert a["acquisition_datetime"].endswith("Z") and a["storage_reference"].startswith("uploads/")

        second = upload(
            client, project["id"], geotiff(width=5, height=4, crs="EPSG:4326", transform=from_origin(1, 2, .0002, .0002)),
            sensor="Sentinel-2", acquisition_datetime="2024-05-01T09:00:00+01:00",
            product_level="L2A", processing_baseline="05.10",
            native_band_resolutions=json.dumps({"B02": 10, "B11": 20}), filename="s2.tif",
        )
        assert second.status_code == 201, second.text
        b = second.json()
        assert b["sensor"] == "Sentinel-2" and b["polarization"] is None
        assert b["native_band_resolutions"] == {"B02": 10.0, "B11": 20.0}
        assert b["product_level"] == "L2A" and b["processing_baseline"] == "05.10"
        assert b["width"] == 5 and b["height"] == 4 and b["crs"] == "EPSG:4326"

        undated = upload(client, project["id"], geotiff(), sensor="Sentinel-2", filename="undated.tif")
        assert undated.status_code == 201, undated.text
        listed = client.get(f"/projects/{project['id']}/scenes").json()
        assert [x["source_filename"] for x in listed] == ["s2.tif", "s1.tif", "undated.tif"]
        detail = client.get(f"/projects/{project['id']}/scenes/{a['id']}")
        assert detail.status_code == 200 and detail.json()["id"] == a["id"]
        spatial = client.get(f"/projects/{project['id']}/scenes/{a['id']}/spatial")
        assert spatial.status_code == 200
        assert spatial.json()["grid"]["transform"] == a["transform"]
        assert spatial.json()["grid"]["width"] == 8

    def test_duplicate_acquisition_dates_are_allowed_and_stable(self, client, project):
        acquired = "2024-06-01T00:00:00Z"
        for name in ["dup-a.tif", "dup-b.tif"]:
            response = upload(client, project["id"], geotiff(), sensor="Sentinel-1", acquisition_datetime=acquired, filename=name)
            assert response.status_code == 201, response.text
        names = [scene["source_filename"] for scene in client.get(f"/projects/{project['id']}/scenes").json()]
        again = [scene["source_filename"] for scene in client.get(f"/projects/{project['id']}/scenes").json()]
        assert set(names) == {"dup-a.tif", "dup-b.tif"} and names == again

    def test_metadata_datetime_fallback_and_scene_dataset_naming(self, client, project):
        """A STAC/MTL item carries the acquisition time; the API should read it
        when the form field is absent, and the queryable dataset row must stay
        distinguishable across acquisitions that share a filename."""
        stac = json.dumps({
            "item_id": "S2B_TEST",
            "datetime": "2025-01-02",
            "properties": {"datetime": "2025-01-02T07:42:29.024000Z", "sat:orbit_state": "descending"},
        })
        response = upload(
            client, project["id"], geotiff(), sensor="Sentinel-2",
            acquisition_metadata=stac, filename="merged.tif",
        )
        assert response.status_code == 201, response.text
        scene = response.json()
        assert scene["acquisition_datetime"] is not None
        assert scene["acquisition_datetime"].startswith("2025-01-02T07:42:29")
        # Date-only top-level value only: midnight UTC, never an error.
        date_only = upload(
            client, project["id"], geotiff(), sensor="Sentinel-2",
            acquisition_metadata=json.dumps({"datetime": "2025-03-13"}), filename="merged.tif",
        )
        assert date_only.status_code == 201, date_only.text
        assert date_only.json()["acquisition_datetime"] == "2025-03-13T00:00:00Z"
        datasets = client.get(f"/projects/{project['id']}/dataset").json()
        names = {d["filename"] for d in datasets}
        assert "Sentinel-2 2025-01-02 · merged.tif" in names
        assert "Sentinel-2 2025-03-13 · merged.tif" in names

    def test_explicit_datetime_without_timezone_stays_strict(self, client, project):
        response = upload(
            client, project["id"], geotiff(), sensor="Sentinel-2",
            acquisition_datetime="2025-01-02", filename="strict.tif",
        )
        assert response.status_code == 422
        assert "timezone" in response.json()["detail"]

    def test_first_scene_supplies_a_cold_start_query_dataset(self, client, project):
        created = upload(
            client,
            project["id"],
            geotiff(),
            sensor="Sentinel-2",
            acquisition_datetime="2025-01-02T00:00:00Z",
            filename="first-scene.tif",
        )
        assert created.status_code == 201, created.text
        datasets = client.get(f"/projects/{project['id']}/dataset").json()
        assert len(datasets) == 1
        # Scene-backed datasets carry the acquisition context so the selector
        # can tell N "merged.tif" acquisitions apart.
        assert datasets[0]["filename"] == "Sentinel-2 2025-01-02 · first-scene.tif"
        assert datasets[0]["band_schema"]["declared"] is True

        batch = client.post(
            f"/projects/{project['id']}/query",
            json={
                "strategy": "diversity",
                "dataset_id": datasets[0]["id"],
                "batch_size": 1,
            },
        )
        assert batch.status_code == 200, batch.text
        assert batch.json()["training_run_id"] is None
        assert batch.json()["batch_size"] == 1

    def test_invalid_uploads_do_not_register_or_leave_source(self, client, project):
        bad_suffix = upload(client, project["id"], b"bad", sensor="Sentinel-2", filename="bad.txt")
        assert bad_suffix.status_code == 422
        corrupt = upload(client, project["id"], b"not a tiff", sensor="Sentinel-2", filename="bad.tif")
        assert corrupt.status_code == 422
        bad_metadata = upload(client, project["id"], geotiff(), sensor="Sentinel-1", polarization="XX")
        assert bad_metadata.status_code == 422
        naive_time = upload(client, project["id"], geotiff(), sensor="Sentinel-2", acquisition_datetime="2024-01-01T00:00:00")
        assert naive_time.status_code == 422
        assert client.get(f"/projects/{project['id']}/scenes").json() == []
        storage = Path(client.app.state.settings.storage_dir) / "uploads" / f"project_{project['id']}"
        assert not list(storage.glob("*"))

    def test_empty_and_over_limit_uploads_leave_no_source(self, client, project):
        empty = upload(client, project["id"], b"", sensor="Sentinel-1", filename="empty.tif")
        assert empty.status_code == 422
        client.app.state.settings.max_upload_bytes = 32
        too_large = upload(client, project["id"], geotiff(), sensor="Sentinel-1", filename="large.tif")
        assert too_large.status_code == 413
        assert client.get(f"/projects/{project['id']}/scenes").json() == []
        storage = Path(client.app.state.settings.storage_dir) / "uploads" / f"project_{project['id']}"
        assert not list(storage.glob("*"))

    def test_sensor_specific_metadata_is_validated(self, client, project):
        response = upload(client, project["id"], geotiff(), sensor="Sentinel-2", acquisition_mode="IW")
        assert response.status_code == 422
        assert "Sentinel-1" in response.json()["detail"]

    def test_source_bytes_preserved_and_scene_delete_isolated(self, client, project):
        content = geotiff(mask=True)
        created = upload(client, project["id"], content, sensor="Sentinel-2", filename="original.tif").json()
        another = upload(client, project["id"], geotiff(width=4, height=4), sensor="Sentinel-1", filename="other.tif").json()
        stored_path = Path(client.app.state.settings.storage_dir) / created["storage_reference"]
        assert hashlib.sha256(stored_path.read_bytes()).digest() == hashlib.sha256(content).digest()
        with rasterio.open(io.BytesIO(content)) as original, rasterio.open(stored_path) as persisted:
            assert np.array_equal(original.read_masks(), persisted.read_masks())
        datasets = client.get(f"/projects/{project['id']}/dataset").json()
        alias = next(item for item in datasets if item["filename"] == "original.tif")
        removed = client.delete(f"/projects/{project['id']}/scenes/{created['id']}")
        assert removed.status_code == 204 and stored_path.exists()
        assert client.get(f"/projects/{project['id']}/dataset/{alias['id']}/file").status_code == 200
        # The scene-backed dataset remains usable until its own last reference is deleted.
        assert client.delete(f"/projects/{project['id']}/dataset/{alias['id']}").status_code == 204
        assert not stored_path.exists()
        remaining = client.get(f"/projects/{project['id']}/scenes").json()
        assert [scene["id"] for scene in remaining] == [another["id"]]
        assert client.get(f"/projects/{project['id']}").status_code == 200

    def test_scene_scoping_and_missing_project(self, client, project):
        created = upload(client, project["id"], geotiff(), sensor="Sentinel-1").json()
        assert client.get(f"/projects/99999/scenes/{created['id']}").status_code == 404
        assert client.delete(f"/projects/{project['id']}/scenes/99999").status_code == 404
        response = client.post(
            "/projects/99999/scenes", files={"file": ("a.tif", geotiff())}, data={"sensor": "Sentinel-1"}
        )
        assert response.status_code == 404


def test_raster_metadata_extractor_reports_per_band_and_masks(tmp_path):
    path = tmp_path / "fixture.tif"
    path.write_bytes(geotiff(nodata=0, mask=True))
    info = extract_scene_metadata(path)
    assert info["band_count"] == 2
    assert info["band_names"] == ["B04", "B08"]
    assert info["band_descriptions"] == ["B04", "B08"]
    assert info["band_dtypes"] == ["uint16", "uint16"]
    assert info["nodata_values"] == [0, 0]
    assert info["has_validity_mask"] is True
    assert info["width"] == 8 and info["height"] == 6


def test_grid_comparison_distinguishes_crs_pixel_size_origin_dimensions_and_extent():
    base = {"crs": "EPSG:32631", "transform": [10, 0, 0, 0, -10, 60], "width": 6, "height": 4, "bounds": [0, 20, 60, 60]}
    assert compare_grid_metadata(base, dict(base))["compatible"]
    shifted = {**base, "transform": [10, 0, 10, 0, -10, 60], "bounds": [10, 20, 70, 60]}
    result = compare_grid_metadata(base, shifted)
    assert {item["property"] for item in result["differences"]} >= {"affine_origin", "affine_transform", "spatial_extent"}
    coarser = {**base, "transform": [20, 0, 0, 0, -20, 60], "bounds": [0, -20, 120, 60]}
    assert "pixel_size" in {x["property"] for x in compare_grid_metadata(base, coarser)["differences"]}
    other_crs = {**base, "crs": "EPSG:4326"}
    assert "crs" in {x["property"] for x in compare_grid_metadata(base, other_crs)["differences"]}
    resized = {**base, "width": 5, "bounds": [0, 20, 50, 60]}
    assert {x["property"] for x in compare_grid_metadata(base, resized)["differences"]} >= {"dimensions", "spatial_extent"}


def test_additive_migration_preserves_existing_rsal_project(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, description TEXT, "
        "classes JSON NOT NULL, status VARCHAR(50), created_at DATETIME, updated_at DATETIME)"
    )
    connection.execute(
        "INSERT INTO projects VALUES (1, 'legacy', 'kept', ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (json.dumps(["water", "land"]),),
    )
    connection.commit()
    connection.close()

    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(storage_dir=tmp_path / "storage", database_url=f"sqlite+aiosqlite:///{db_path}", _env_file=None))
    with TestClient(app) as client:
        response = client.get("/projects/1")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["classes"] == ["water", "land"] and body["description"] == "kept"
        assert body["classification_config"]["internal_classes"] == ["open_water", "emergent_vegetation", "land"]
    with TestClient(app) as client:
        assert client.get("/projects/1").json()["classes"] == ["water", "land"]
    connection = sqlite3.connect(db_path)
    # Every additive migration must have run exactly once, and running the app a
    # second time must not add duplicates.
    assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [
        (1,),
        (2,),
        (3,),
        (4,),
        (5,),
        (6,),
        (7,),
        (8,),
        (9,),
        (10,),
        (11,),
        (12,),
    ]
    columns = {row[1] for row in connection.execute("PRAGMA table_info(projects)")}
    assert {"study_area_geometry", "study_area_crs", "classification_config"}.issubset(columns)
    dataset_columns = {row[1] for row in connection.execute("PRAGMA table_info(datasets)")}
    assert "band_schema" in dataset_columns
    # Phase 1 additions are additive too, and the legacy project did not acquire
    # water semantics it never opted into.
    assert "taxonomy" in columns
    # Phase 5 tables exist and are equally additive.
    research_tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "evaluation_protocols",
        "evaluation_results",
        "reference_areas",
        "research_plans",
        "research_reports",
    }.issubset(research_tables)
    assert "submitted_class_name" in {
        row[1] for row in connection.execute("PRAGMA table_info(labels)")
    }
    assert connection.execute("SELECT taxonomy FROM projects").fetchone() == (None,)
    # Phase 2 adds durable sampling records; the legacy label keeps manual
    # provenance (no batch link is invented for it).
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"query_batches", "query_items"}.issubset(tables)
    # Phase 3 lineage: legacy rows keep NULL content identities rather than being
    # hashed after the fact.
    dataset_columns = {row[1] for row in connection.execute("PRAGMA table_info(datasets)")}
    assert {"content_sha256", "size_bytes"}.issubset(dataset_columns)
    run_columns = {row[1] for row in connection.execute("PRAGMA table_info(training_runs)")}
    assert {"manifest", "checkpoint_sha256", "experiment_id"}.issubset(run_columns)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "experiments" in tables
    label_columns = {row[1] for row in connection.execute("PRAGMA table_info(labels)")}
    assert {"query_batch_id", "query_item_id"}.issubset(label_columns)
    assert connection.execute("SELECT COUNT(*) FROM labels WHERE query_item_id IS NOT NULL").fetchone() == (0,)
    connection.close()


def test_versioned_migration_explicitly_creates_scene_table(tmp_path):
    import asyncio
    from sqlalchemy import inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.migrations.v001_scene_foundation import upgrade

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'migration-only.db'}")
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
            await upgrade(connection)
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            assert "scenes" in tables
            columns = await connection.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("projects")})
            assert {"study_area_geometry", "study_area_crs", "classification_config"}.issubset(columns)
        await engine.dispose()

    asyncio.run(run())
