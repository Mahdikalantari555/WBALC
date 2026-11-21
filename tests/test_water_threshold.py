"""Model-free Otsu water-threshold product: service and endpoint scenarios."""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.water_threshold_service import (
    WaterThresholdError,
    compute_water_threshold,
    otsu_threshold,
    resolve_index,
    values_to_json,
)


def two_band_tiff(first: np.ndarray, second: np.ndarray, names: tuple[str, str], nodata=None) -> io.BytesIO:
    buffer = io.BytesIO()
    height, width = first.shape
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=2,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(500000, 4649776, 10, 10),
        nodata=nodata,
    ) as dst:
        dst.write(first, 1)
        dst.write(second, 2)
        dst.set_band_description(1, names[0])
        dst.set_band_description(2, names[1])
    buffer.seek(0)
    return buffer


def write_tiff(buffer: io.BytesIO, tmp_path, name="scene.tif") -> str:
    path = tmp_path / name
    path.write_bytes(buffer.read())
    return str(path)


class TestOtsu:
    def test_bimodal_separation(self):
        values = np.concatenate([np.full(500, 0.9), np.full(500, -0.9)])
        threshold = otsu_threshold(values)
        assert -0.1 < threshold < 0.1

    def test_constant_field_returns_the_value(self):
        assert otsu_threshold(np.full(100, 0.25)) == pytest.approx(0.25)

    def test_empty_input_is_rejected(self):
        with pytest.raises(WaterThresholdError):
            otsu_threshold(np.array([], dtype=float))


class TestResolveIndex:
    def test_sensor_defaults(self):
        assert resolve_index("Sentinel-2", None) == "ndwi"
        assert resolve_index("Sentinel-1", None) == "vv"
        assert resolve_index("Sentinel-1", "auto") == "vv"

    def test_unknown_sensor_needs_explicit_index(self):
        with pytest.raises(WaterThresholdError):
            resolve_index("Landsat", None)

    def test_unknown_index_is_rejected(self):
        with pytest.raises(WaterThresholdError):
            resolve_index("Sentinel-2", "awei")


class TestComputeWaterThreshold:
    def test_ndwi_marks_high_index_pixels_as_water(self, tmp_path):
        green = np.full((20, 30), 1200.0, dtype="float32")
        nir = np.full((20, 30), 400.0, dtype="float32")
        # Water block: green >> nir → NDWI ≈ +0.5; land block: ≈ −0.43.
        green[0:10, :] = 1500.0
        nir[0:10, :] = 200.0
        path = write_tiff(two_band_tiff(green, nir, ("green", "nir08")), tmp_path)

        result = compute_water_threshold(path, "ndwi", ["green", "nir08"], [None, None])
        assert result.index == "ndwi" and result.direction == "above"
        assert result.method == "otsu"
        assert result.threshold > 0.0
        assert result.counts["water"] == 10 * 30
        assert result.counts["non_water"] == 10 * 30
        assert result.values[2, 5] == 1 and result.values[15, 5] == 0
        # Water area in m²: 300 pixels × 10 m × 10 m.
        assert result.areas["water_sqm"] == pytest.approx(300 * 100.0)
        assert result.grid["crs"] == "EPSG:32638"

    def test_missing_band_is_actionable(self, tmp_path):
        green = np.full((8, 8), 1000.0, dtype="float32")
        red = np.full((8, 8), 500.0, dtype="float32")
        path = write_tiff(two_band_tiff(green, red, ("green", "red")), tmp_path)
        with pytest.raises(WaterThresholdError, match="nir08"):
            compute_water_threshold(path, "ndwi", ["green", "red"], [None, None])

    def test_sar_water_is_below_threshold(self, tmp_path):
        buffer = io.BytesIO()
        vv = np.full((20, 20), 900.0, dtype="float32")
        vv[0:10, :] = 150.0  # dark open water
        with rasterio.open(
            buffer, "w", driver="GTiff", width=20, height=20, count=1, dtype="float32",
            crs="EPSG:32638", transform=from_origin(500000, 4649776, 10, 10),
        ) as dst:
            dst.write(vv, 1)
            dst.set_band_description(1, "vv")
        buffer.seek(0)
        path = write_tiff(buffer, tmp_path, name="sar.tif")

        result = compute_water_threshold(path, "vv", ["vv"], [None])
        assert result.direction == "below"
        assert result.counts["water"] == 10 * 20
        assert result.values[15, 10] == 0

    def test_nodata_and_study_area_exclude_pixels(self, tmp_path):
        green = np.full((20, 20), 300.0, dtype="float32")
        nir = np.full((20, 20), 1200.0, dtype="float32")  # land-like NDWI ≈ −0.6
        green[0:10, 0:10] = 1500.0
        nir[0:10, 0:10] = 200.0  # water-like NDWI ≈ +0.77 in the top-left block
        green[0, :] = 0.0
        nir[0, :] = 0.0  # nodata row (overrides the block's first row)
        path = write_tiff(two_band_tiff(green, nir, ("green", "nir08"), nodata=0.0), tmp_path)
        area = np.ones((20, 20), dtype=bool)
        area[:, 10:] = False  # study area covers the left half only

        result = compute_water_threshold(path, "ndwi", ["green", "nir08"], [0.0, 0.0], study_area=area)
        # Valid: rows 1..19 × cols 0..9 (nodata row + right half excluded).
        assert result.counts["valid"] == 19 * 10
        row = values_to_json(result.values)[0]
        assert all(value is None for value in row)  # nodata row invalid everywhere
        assert result.values[5, 12] == -1  # outside the study area
        assert result.values[5, 5] == 1  # water inside the study area
        assert result.values[15, 5] == 0  # land inside the study area
        assert result.counts["water"] == 9 * 10

    def test_all_nodata_scene_is_rejected(self, tmp_path):
        green = np.zeros((8, 8), dtype="float32")
        nir = np.zeros((8, 8), dtype="float32")
        path = write_tiff(two_band_tiff(green, nir, ("green", "nir08"), nodata=0.0), tmp_path)
        with pytest.raises(WaterThresholdError, match="No valid pixels"):
            compute_water_threshold(path, "ndwi", ["green", "nir08"], [0.0, 0.0])
