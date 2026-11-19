"""Shared fixtures: isolated app + client + synthetic multi-band GeoTIFF."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        patch_size=8,
        stride=8,
        _env_file=None,
    )


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def geotiff_bytes() -> bytes:
    """64x64, 4-band GeoTIFF in EPSG:32631; left half 'water-like', right half 'veg-like'."""
    rng = np.random.default_rng(7)
    h = w = 64
    data = np.zeros((4, h, w), dtype=np.float32)
    # class-separable spectral signatures + noise
    data[:, :, :32] = np.array([10, 20, 100, 120], dtype=np.float32)[:, None, None] + rng.normal(0, 2, (4, h, 32))
    data[:, :, 32:] = np.array([80, 90, 30, 150], dtype=np.float32)[:, None, None] + rng.normal(0, 2, (4, h, 32))
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=4,
        dtype="float32",
        crs="EPSG:32631",
        transform=from_origin(500000, 4649776, 10, 10),
    ) as dst:
        dst.write(data)
    return buf.getvalue()


@pytest.fixture()
def project(client) -> dict:
    # A generic two-class project: it opts out of the WBALC water taxonomy on
    # purpose, so these legacy-path tests keep their own class list. Water-taxonomy
    # projects are created explicitly in the Phase 1 tests.
    resp = client.post(
        "/projects",
        json={
            "name": "Demo",
            "classes": ["water", "vegetation"],
            "description": "test",
            "status": "active",
            "generic_classes": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# The shared fixture declares its bands explicitly: a raster with unnamed bands
# is now "schema undeclared", and training/inference on it requires an override.
# Tests that want the undeclared path upload without these fields on purpose.
BAND_NAMES = "blue,green,red,nir"


@pytest.fixture()
def dataset(client, project, geotiff_bytes) -> dict:
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("scene.tif", geotiff_bytes, "image/tiff")},
        data={"band_names": BAND_NAMES, "sensor": "sentinel-2"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def point_label(x: float, y: float, class_name: str, iteration: int = 0, **kw) -> dict:
    return {
        "geometry": {"type": "Point", "coordinates": [x, y]},
        "class_name": class_name,
        "iteration": iteration,
        **kw,
    }


@pytest.fixture()
def labeled(client, project, dataset):
    """Label 12 water + 12 vegetation patch centers across the scene."""
    labels = []
    for row in range(8):
        for col in range(8):
            x, y = col * 8 + 4, row * 8 + 4
            cls = "water" if col < 4 else "vegetation"
            labels.append(point_label(x, y, cls))
    resp = client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
    assert resp.status_code == 201, resp.text
    return resp.json()