"""Bounded raster preview API coverage for datasets and scenes."""
from __future__ import annotations

import io

from PIL import Image


def test_dataset_preview_is_bounded_and_supports_windows(client, project, dataset):
    root = f"/projects/{project['id']}/dataset/{dataset['id']}/preview"
    preview = client.get(root, params={"mode": "true-color", "size": 32})
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(preview.content)) as image:
        assert image.size == (32, 32)
        assert image.mode == "RGBA"

    window = client.get(root, params={
        "mode": "band:0", "size": 64, "x0": 4, "y0": 8, "x1": 16, "y1": 20, "upscale": "true",
    })
    assert window.status_code == 200, window.text
    with Image.open(io.BytesIO(window.content)) as image:
        assert image.size == (64, 64)

    assert client.get(root, params={"x0": 0, "y0": 0, "x1": 10}).status_code == 422
    outside = client.get(root, params={"x0": 60, "y0": 60, "x1": 70, "y1": 70})
    assert outside.status_code == 422

    probe = client.get(f"/projects/{project['id']}/dataset/{dataset['id']}/pixel", params={
        "x": 10, "y": 10, "mode": "ndvi",
    })
    assert probe.status_code == 200, probe.text
    assert [band["name"] for band in probe.json()["bands"]] == ["nir", "red"]
    first, second = [band["value"] for band in probe.json()["bands"]]
    assert probe.json()["index"] == (first - second) / (first + second)
    assert client.get(f"/projects/{project['id']}/dataset/{dataset['id']}/pixel", params={"x": 64, "y": 0}).status_code == 422

    other_project = client.post("/projects", json={"name": "not owner"}).json()["id"]
    assert client.get(f"/projects/{other_project}/dataset/{dataset['id']}/preview").status_code == 404


def test_scene_preview_renders_named_ndvi_and_enforces_project_scope(client, project, geotiff_bytes):
    created = client.post(
        f"/projects/{project['id']}/scenes",
        files={"file": ("preview-scene.tif", geotiff_bytes, "image/tiff")},
        data={"sensor": "Sentinel-2", "band_names": "blue,green,red,nir"},
    )
    assert created.status_code == 201, created.text
    scene_id = created.json()["id"]

    response = client.get(f"/projects/{project['id']}/scenes/{scene_id}/preview", params={"mode": "ndvi", "size": 48})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (48, 48)
        assert image.mode == "RGBA"

    probe = client.get(f"/projects/{project['id']}/scenes/{scene_id}/pixel", params={
        "x": 4, "y": 5, "mode": "band:0",
    })
    assert probe.status_code == 200, probe.text
    assert probe.json()["bands"][0]["name"] == "blue"
    assert isinstance(probe.json()["bands"][0]["value"], float)
    assert probe.json()["difference"] is False and probe.json()["index"] is None

    other_project = client.post("/projects", json={"name": "not owner"}).json()["id"]
    assert client.get(f"/projects/{other_project}/scenes/{scene_id}/preview").status_code == 404
