"""dataset-ingestion spec scenarios."""

from __future__ import annotations

import pytest


class TestDatasets:
    def test_upload_geotiff_metadata(self, client, project, geotiff_bytes):
        resp = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": ("scene.tif", geotiff_bytes, "image/tiff")},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["project_id"] == project["id"]
        assert body["crs"] == "EPSG:32631"
        assert body["width"] == 64 and body["height"] == 64
        assert body["bands"] == 4 > 1  # multi-band requirement
        assert body["dtype"] == "float32"
        assert len(body["transform"]) == 6
        assert body["transform"][0] == pytest.approx(10.0)
        assert len(body["bounds"]) == 4

    def test_upload_rejects_non_tiff(self, client, project):
        resp = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 422

    def test_upload_rejects_corrupt_tiff(self, client, project):
        resp = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": ("bad.tif", b"not really a tiff", "image/tiff")},
        )
        assert resp.status_code == 422

    def test_upload_missing_project_404(self, client, geotiff_bytes):
        resp = client.post(
            "/projects/9999/upload", files={"file": ("s.tif", geotiff_bytes, "image/tiff")}
        )
        assert resp.status_code == 404

    def test_list_datasets(self, client, project, dataset):
        resp = client.get(f"/projects/{project['id']}/dataset")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == dataset["id"]
        assert items[0]["bands"] == 4

    def test_get_single_dataset(self, client, project, dataset):
        resp = client.get(f"/projects/{project['id']}/dataset/{dataset['id']}")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "scene.tif"
        assert client.get(f"/projects/{project['id']}/dataset/9999").status_code == 404
