"""Unit tests for raster / grid / geometry helpers."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.raster_service import (
    make_grid,
    map_to_pixel,
    parse_sample_id,
    patch_features,
    pixel_features,
    pixel_to_map,
    points_in_polygon,
    validate_grid_compatibility,
    RasterError,
    sample_id,
)


class TestGrid:
    def test_exact_fit(self):
        grid = make_grid(64, 64, 8, 8)
        assert grid.shape == (8, 8)
        assert grid.ys == list(range(0, 64, 8))

    def test_edge_clamped(self):
        grid = make_grid(67, 64, 8, 8)
        rows, cols = grid.shape
        assert rows == 9 and cols == 8
        assert grid.ys[-1] == 59  # clamped so 59+8 covers row 66
        assert grid.ys[-1] + grid.patch_h == 67

    def test_image_smaller_than_patch(self):
        grid = make_grid(5, 7, 8, 8)
        assert grid.shape == (1, 1)
        assert grid.patch_h == 5 and grid.patch_w == 7

    def test_overlapping_stride(self):
        grid = make_grid(16, 16, 8, 4)
        assert grid.shape == (3, 3)

    def test_sample_id_roundtrip(self):
        assert parse_sample_id(sample_id(3, 2, 5)) == (3, 2, 5)
        assert parse_sample_id("not-a-patch") is None


class TestFeatures:
    def test_shape_and_values(self):
        arr = np.ones((4, 16, 16), dtype=np.float32) * 5
        grid = make_grid(16, 16, 8, 8)
        feats = patch_features(arr, grid)
        assert feats.shape == (4, 16)  # 4 patches x 4 bands x 4 stats
        f = feats[0].reshape(4, 4)  # stats x bands
        assert np.allclose(f[0], 5)  # mean
        assert np.allclose(f[1], 0)  # std
        assert np.allclose(f[2], 5)  # min
        assert np.allclose(f[3], 5)  # max

    def test_nan_robust(self):
        arr = np.full((2, 8, 8), np.nan, dtype=np.float32)
        grid = make_grid(8, 8, 8, 8)
        feats = patch_features(arr, grid)
        assert np.isfinite(feats).all()

    def test_pixel_features_keep_pixel_order_and_mask_invalid(self):
        arr = np.arange(2 * 3 * 5, dtype=np.float32).reshape(2, 3, 5)
        arr[1, 1, 2] = np.nan
        feats, valid = pixel_features(arr)
        assert feats.shape == (15, 2)
        assert feats[0].tolist() == [0.0, 15.0]
        assert valid.reshape(3, 5)[1, 2] == False
        assert feats[7].tolist() == [7.0, 0.0]  # preserve other band; mask controls use

    def test_patch_validity_does_not_miss_sparse_valid_edge(self):
        from app.services.raster_service import patch_validity
        arr = np.full((1, 8, 8), np.nan, dtype=np.float32)
        arr[0, 1, 1] = 7
        grid = make_grid(8, 8, 8, 8)
        assert patch_validity(arr, grid).tolist() == [True]


class TestGeo:
    def test_grid_compatibility_checks_exact_reference_grid(self, tmp_path):
        import rasterio
        from rasterio.transform import from_origin

        path_a, path_b = tmp_path / "a.tif", tmp_path / "b.tif"
        profile = dict(driver="GTiff", width=5, height=3, count=1, dtype="uint8", crs="EPSG:32632", transform=from_origin(500000, 500100, 10, 20))
        with rasterio.open(path_a, "w", **profile) as dst:
            dst.write(np.ones((1, 3, 5), dtype=np.uint8))
        with rasterio.open(path_b, "w", **profile) as dst:
            dst.write(np.ones((1, 3, 5), dtype=np.uint8))
        with rasterio.open(path_a) as ref, rasterio.open(path_b) as candidate:
            validate_grid_compatibility(ref, candidate)
        bad = dict(profile, transform=from_origin(500001, 500100, 10, 20))
        with rasterio.open(path_b, "w", **bad) as dst:
            dst.write(np.ones((1, 3, 5), dtype=np.uint8))
        with rasterio.open(path_a) as ref, rasterio.open(path_b) as candidate:
            with pytest.raises(RasterError, match="transform"):
                validate_grid_compatibility(ref, candidate)

    def test_map_pixel_roundtrip(self):
        transform = [10.0, 0.0, 500000.0, 0.0, -10.0, 4649776.0]
        col, row = map_to_pixel(transform, 500040.0, 4649736.0)
        assert col == pytest.approx(4.0)
        assert row == pytest.approx(4.0)
        x, y = pixel_to_map(transform, col, row)
        assert x == pytest.approx(500040.0)
        assert y == pytest.approx(4649736.0)

    def test_points_in_polygon(self):
        square = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]
        xs = np.array([5.0, 15.0, 0.5])
        ys = np.array([5.0, 5.0, 0.5])
        assert points_in_polygon(xs, ys, square).tolist() == [True, False, True]

    def test_polygon_with_hole(self):
        rings = [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ]
        xs = np.array([5.0, 2.0])
        ys = np.array([5.0, 2.0])
        assert points_in_polygon(xs, ys, rings).tolist() == [False, True]
