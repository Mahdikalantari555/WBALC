"""label-management spec scenarios."""

from __future__ import annotations

import pytest

from .conftest import point_label


class TestLabels:
    def test_submit_point_label(self, client, project, dataset):
        resp = client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "water"))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["sample_type"] == "point"
        assert body["class_name"] == "water"
        assert body["version"] == 1
        assert body["sample_id"] == f"d{dataset['id']}_r0_c0"

    def test_submit_polygon_label(self, client, project, dataset):
        poly = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [16, 0], [16, 16], [0, 16], [0, 0]]],
            },
            "class_name": "water",
        }
        resp = client.post(f"/projects/{project['id']}/labels", json=poly)
        assert resp.status_code == 201
        assert resp.json()["sample_type"] == "polygon"

    def test_unknown_class_rejected(self, client, project, dataset):
        resp = client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "cloud"))
        assert resp.status_code == 422

    def test_correction_versions(self, client, project, dataset):
        r1 = client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "water", iteration=0))
        r2 = client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "vegetation", iteration=1))
        assert r1.status_code == r2.status_code == 201
        b1, b2 = r1.json(), r2.json()
        assert b1["sample_id"] == b2["sample_id"]  # same patch -> same sample
        assert b2["version"] == b1["version"] + 1
        assert b2["iteration"] == 1
        assert b2["class_name"] == "vegetation"

        current = client.get(f"/projects/{project['id']}/labels").json()
        assert len(current) == 1
        assert current[0]["class_name"] == "vegetation"  # latest wins

    def test_history_keeps_all_versions(self, client, project, dataset):
        client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "water", 0))
        client.post(f"/projects/{project['id']}/labels", json=point_label(4, 4, "vegetation", 1))
        client.post(f"/projects/{project['id']}/labels", json=point_label(60, 60, "vegetation", 0))
        resp = client.get(f"/projects/{project['id']}/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 3  # full history, including the superseded label
        versions = [h["version"] for h in history if h["sample_id"] == f"d{dataset['id']}_r0_c0"]
        assert sorted(versions) == [1, 2]

    def test_batch_submit(self, client, project, dataset):
        resp = client.post(
            f"/projects/{project['id']}/labels",
            json={"labels": [point_label(4, 4, "water"), point_label(60, 60, "vegetation")]},
        )
        assert resp.status_code == 201
        assert len(resp.json()["labels"]) == 2
        assert resp.json()["training"] is None

    def test_map_space_label(self, client, project, dataset):
        # pixel (4,4) -> map (500040, 4649736) with 10m pixels
        lbl = point_label(500044.0, 4649732.0, "water", coordinate_space="map")
        resp = client.post(f"/projects/{project['id']}/labels", json=lbl)
        assert resp.status_code == 201
        assert resp.json()["sample_id"] == f"d{dataset['id']}_r0_c0"

    def test_out_of_bounds_point_and_invalid_polygon_rejected(self, client, project, dataset):
        outside = client.post(f"/projects/{project['id']}/labels", json=point_label(64, 10, "water"))
        assert outside.status_code == 422
        malformed = client.post(f"/projects/{project['id']}/labels", json={
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 4]]]},
            "class_name": "water",
        })
        assert malformed.status_code == 422
        assert client.get(f"/projects/{project['id']}/labels").json() == []

    def test_pixel_sample_identity_is_not_patch_identity(self, client, project, dataset):
        a = client.post(f"/projects/{project['id']}/labels", json=point_label(1, 1, "water", sample_resolution="pixel"))
        b = client.post(f"/projects/{project['id']}/labels", json=point_label(2, 2, "vegetation", sample_resolution="pixel"))
        assert a.status_code == b.status_code == 201
        assert a.json()["sample_id"] != b.json()["sample_id"]

    def test_map_label_declared_crs_is_reprojected_to_dataset(self, client, project, dataset):
        from rasterio.warp import transform
        lon, lat = transform("EPSG:32631", "EPSG:4326", [500044.0], [4649732.0])
        response = client.post(f"/projects/{project['id']}/labels", json=point_label(
            lon[0], lat[0], "water", coordinate_space="map", coordinate_crs="EPSG:4326"
        ))
        assert response.status_code == 201, response.text
        assert response.json()["sample_id"] == f"d{dataset['id']}_r0_c0"
        assert response.json()["geometry"]["coordinates"][0] == pytest.approx(500044.0, abs=0.01)

    def test_self_intersecting_polygon_rejected(self, client, project, dataset):
        response = client.post(f"/projects/{project['id']}/labels", json={
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [8, 8], [0, 8], [8, 0], [0, 0]]]},
            "class_name": "water",
        })
        assert response.status_code == 422

    def test_labels_missing_project_404(self, client):
        assert client.post("/projects/9999/labels", json=point_label(1, 1, "water")).status_code == 404
        assert client.get("/projects/9999/history").status_code == 404
