"""Tests for add-terralab-frontend backend additions.

Covers: raw file access, extended metadata, dataset deletion, label deletion.
"""

from __future__ import annotations

import io
from pathlib import Path

import rasterio

from .conftest import point_label


class TestDatasetFile:
    def test_download_original(self, client, project, dataset, geotiff_bytes):
        resp = client.get(f"/projects/{project['id']}/dataset/{dataset['id']}/file")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/tiff")
        assert resp.content == geotiff_bytes  # byte-identical original
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            assert ds.count == 4 and ds.width == 64

    def test_download_missing_dataset_404(self, client, project):
        assert client.get(f"/projects/{project['id']}/dataset/9999/file").status_code == 404

    def test_download_missing_file_404(self, client, project, dataset, settings):
        Path(dataset["path"] if "path" in dataset else next(
            iter((settings.storage_dir / "uploads" / f"project_{project['id']}").glob("*.tif"))
        )).unlink()
        assert client.get(f"/projects/{project['id']}/dataset/{dataset['id']}/file").status_code == 404


class TestExtendedMetadata:
    def test_upload_includes_size_and_grid(self, client, project, geotiff_bytes):
        resp = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": ("scene.tif", geotiff_bytes, "image/tiff")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["size_bytes"] == len(geotiff_bytes)
        grid = body["patch_grid"]
        assert grid["patch_size"] == 8 and grid["stride"] == 8  # test settings
        assert grid["rows"] == 8 and grid["cols"] == 8
        assert grid["total_patches"] == 64

    def test_list_and_get_include_extensions(self, client, project, dataset):
        for url in (
            f"/projects/{project['id']}/dataset",
            f"/projects/{project['id']}/dataset/{dataset['id']}",
        ):
            resp = client.get(url)
            assert resp.status_code == 200
            items = resp.json()
            item = items[0] if isinstance(items, list) else items
            assert item["size_bytes"] > 0
            assert item["patch_grid"]["total_patches"] == 64


class TestDatasetDeletion:
    def test_delete_dataset_cascades(self, client, project, dataset, settings):
        pid, did = project["id"], dataset["id"]
        client.post(f"/projects/{pid}/labels", json=point_label(4, 4, "water"))
        assert len(client.get(f"/projects/{pid}/history").json()) == 1

        resp = client.delete(f"/projects/{pid}/dataset/{did}")
        assert resp.status_code == 204
        assert client.get(f"/projects/{pid}/dataset/{did}").status_code == 404
        assert client.get(f"/projects/{pid}/dataset").json() == []
        assert client.get(f"/projects/{pid}/history").json() == []  # labels removed
        assert not list((settings.storage_dir / "uploads" / f"project_{pid}").glob("*.tif"))

    def test_delete_missing_404(self, client, project):
        assert client.delete(f"/projects/{project['id']}/dataset/9999").status_code == 404


class TestLabelDeletion:
    def test_delete_all_versions(self, client, project, dataset):
        pid = project["id"]
        r1 = client.post(f"/projects/{pid}/labels", json=point_label(4, 4, "water", 0))
        sid = r1.json()["sample_id"]
        client.post(f"/projects/{pid}/labels", json=point_label(4, 4, "vegetation", 1))
        client.post(f"/projects/{pid}/labels", json=point_label(60, 60, "vegetation"))
        assert len(client.get(f"/projects/{pid}/history").json()) == 3

        resp = client.delete(f"/projects/{pid}/labels/{sid}")
        assert resp.status_code == 204
        history = client.get(f"/projects/{pid}/history").json()
        assert len(history) == 1
        assert all(h["sample_id"] != sid for h in history)

    def test_delete_unknown_sample_404(self, client, project, dataset):
        assert client.delete(f"/projects/{project['id']}/labels/nope").status_code == 404
