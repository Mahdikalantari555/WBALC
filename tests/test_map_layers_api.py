"""Map-layer contracts: classification/uncertainty fields, exports, palettes, geometry."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services.inference_service import (
    CLASS_PALETTE,
    UNCERTAINTY_RAMP,
    ramp_color,
    uncertainty_colors,
)

FRONTEND_PALETTE = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "palette.ts"
)
FRONTEND_OVERLAY = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "overlay.ts"
)


def _train(client, project_id: int) -> dict:
    resp = client.post(f"/projects/{project_id}/train", json={"model_type": "rf"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _nodata_dataset(client, project_id: int) -> dict:
    """A scene whose left half is entirely nodata (a rotated-image collar)."""
    rng = np.random.default_rng(3)
    h = w = 64
    data = np.zeros((4, h, w), dtype=np.float32)
    data[:, :, 32:] = np.array([80, 90, 30, 150], dtype=np.float32)[:, None, None] + rng.normal(
        0, 2, (4, h, 32)
    )
    buffer = io.BytesIO()
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=4,
        dtype="float32",
        crs="EPSG:32631",
        transform=from_origin(500000, 4649776, 10, 10),
        nodata=0,
    ) as dst:
        dst.write(data)
    resp = client.post(
        f"/projects/{project_id}/upload",
        files={"file": ("collar.tif", buffer.getvalue(), "image/tiff")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestMapField:
    def test_hard_layer_shape_and_values(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/predict/map", params={"layer": "hard"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        rows, cols = body["grid"]["rows"], body["grid"]["cols"]
        assert (rows, cols) == (8, 8)
        assert len(body["values"]) == rows and len(body["values"][0]) == cols
        flat = [v for row in body["values"] for v in row]
        assert set(flat) <= {0, 1}
        assert all(v is True for row in body["valid"] for v in row)
        assert body["layer"] == "hard"
        assert body["method"] is None
        assert body["min"] == 0 and body["max"] == 1

    def test_uncertainty_layer_is_bounded_and_ranked(self, client, project, dataset, labeled):
        _train(client, project["id"])
        body = client.get(
            f"/projects/{project['id']}/predict/map",
            params={"layer": "uncertainty", "method": "entropy"},
        ).json()
        values = [v for row in body["values"] for v in row if v is not None]
        assert values and all(0.0 <= v <= 1.0 for v in values)
        assert body["method"] == "entropy"
        assert body["min"] <= min(values) + 1e-6 and body["max"] >= max(values) - 1e-6

    def test_uncertainty_map_agrees_with_query_ranking(self, client, project, dataset, labeled):
        _train(client, project["id"])
        field = client.get(
            f"/projects/{project['id']}/predict/map",
            params={"layer": "uncertainty", "method": "entropy", "dataset_id": dataset["id"]},
        ).json()
        batch = client.post(
            f"/projects/{project['id']}/query",
            json={
                "strategy": "uncertainty",
                "method": "entropy",
                "batch_size": 5,
                "exclude_labeled": False,  # this fixture labels every patch
            },
        ).json()
        assert batch["samples"], "expected an uncertainty batch"
        ranked = [
            (field["values"][s["coords"]["row"]][s["coords"]["col"]], s["sample_id"])
            for s in batch["samples"]
        ]
        # The batch is the top of the same field it is drawn from: the lowest
        # selected value must beat the field's median.
        all_values = sorted(v for row in field["values"] for v in row if v is not None)
        median = all_values[len(all_values) // 2]
        assert min(v for v, _ in ranked) >= median - 1e-6, ranked

    def test_unknown_method_422(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(
            f"/projects/{project['id']}/predict/map",
            params={"layer": "uncertainty", "method": "vibes"},
        )
        assert resp.status_code == 422

    def test_unknown_layer_422(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/predict/map", params={"layer": "ndvi"})
        assert resp.status_code == 422

    def test_requires_model(self, client, project, dataset):
        assert client.get(f"/projects/{project['id']}/predict/map").status_code == 409

    def test_staleness_flag(self, client, project, dataset, labeled):
        first = _train(client, project["id"])
        fresh = client.get(f"/projects/{project['id']}/predict/map").json()
        assert fresh["stale"] is False
        assert fresh["model_iteration"] == first["iteration"]

        extra = client.post(
            f"/projects/{project['id']}/labels",
            json={
                "labels": [
                    {
                        "geometry": {"type": "Point", "coordinates": [36, 4]},
                        "class_name": "water",
                        "iteration": first["iteration"],
                    }
                ]
            },
        )
        assert extra.status_code == 201
        _train(client, project["id"])

        old = client.get(
            f"/projects/{project['id']}/predict/map",
            params={"iteration": first["iteration"]},
        ).json()
        assert old["stale"] is True

    def test_invalid_patches_are_marked_not_painted(self, client, project, labeled):
        nodata = _nodata_dataset(client, project["id"])
        # label only the valid half
        labels = [
            {
                "geometry": {"type": "Point", "coordinates": [col * 8 + 4, row * 8 + 4]},
                "class_name": "vegetation",
                "dataset_id": nodata["id"],
            }
            for row in range(8)
            for col in range(4, 8)
        ]
        labels.append(
            {
                "geometry": {"type": "Point", "coordinates": [4, 4]},
                "class_name": "water",
                "dataset_id": nodata["id"],
            }
        )
        assert (
            client.post(f"/projects/{project['id']}/labels", json={"labels": labels}).status_code
            == 201
        )
        _train(client, project["id"])
        body = client.get(
            f"/projects/{project['id']}/predict/map", params={"dataset_id": nodata["id"]}
        ).json()
        # columns 0-3 are entirely nodata -> invalid, never classified
        for row in range(8):
            for col in range(4):
                assert body["valid"][row][col] is False
                assert body["values"][row][col] is None
        assert any(body["valid"][row][7] for row in range(8))


class TestReadOnlyPaths:
    """Map layers and PNG/CSV previews must never write GeoTIFFs."""

    def test_map_field_does_not_persist_exports(self, client, project, dataset, labeled):
        _train(client, project["id"])
        before = len(client.get(f"/projects/{project['id']}/exports").json())
        for method in ("entropy", "margin"):
            for layer in ("hard", "uncertainty"):
                assert (
                    client.get(
                        f"/projects/{project['id']}/predict/map",
                        params={"layer": layer, "method": method, "dataset_id": dataset["id"]},
                    ).status_code
                    == 200
                )
        after = len(client.get(f"/projects/{project['id']}/exports").json())
        assert after == before

    def test_csv_and_png_do_not_persist_exports(self, client, project, dataset, labeled):
        pytest.importorskip("PIL")
        _train(client, project["id"])
        before = len(client.get(f"/projects/{project['id']}/exports").json())
        client.get(f"/projects/{project['id']}/exports/hard.csv")
        client.get(f"/projects/{project['id']}/exports/uncertainty.png")
        after = len(client.get(f"/projects/{project['id']}/exports").json())
        assert after == before

    def test_export_listing_collapses_duplicates(self, client, project, dataset, labeled):
        _train(client, project["id"])
        for _ in range(3):
            client.post(f"/projects/{project['id']}/predict", json={})
        rows = client.get(f"/projects/{project['id']}/exports").json()
        keys = [(r["dataset_id"], r["type"], r["method"]) for r in rows]
        assert len(keys) == len(set(keys)), keys
        assert {r["type"] for r in rows} == {"hard", "probability", "uncertainty"}
        assert all(r["iteration"] == 0 and r["dataset_name"] == "scene.tif" for r in rows)


class TestExports:
    def test_uncertainty_geotiff(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(
            f"/projects/{project['id']}/download/uncertainty", params={"method": "margin"}
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/tiff")
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            assert ds.count == 1
            assert ds.dtypes[0] == "float32"
            assert ds.tags()["method"] == "margin"
            assert json.loads(ds.tags()["classes"]) == ["water", "vegetation"]
            arr = ds.read(1)
            # Patch cells cover the source grid: 8x8 cells x 8 px = 64x64.
            assert arr.shape == (64, 64)
            finite = arr[arr != ds.nodata]
            assert finite.size and finite.min() >= 0.0 and finite.max() <= 1.0
            assert ds.descriptions == ("margin",)

    def test_uncertainty_export_method_filters(self, client, project, dataset, labeled):
        _train(client, project["id"])
        client.get(f"/projects/{project['id']}/download/uncertainty", params={"method": "entropy"})
        resp = client.get(
            f"/projects/{project['id']}/download/uncertainty", params={"method": "least_confidence"}
        )
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            assert ds.tags()["method"] == "least_confidence"

    def test_unknown_export_type_lists_valid_types(self, client, project):
        resp = client.get(f"/projects/{project['id']}/download/bogus")
        assert resp.status_code == 404
        assert "uncertainty" in resp.json()["detail"]

    def test_hard_colormap_matches_ui_palette(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/download/hard")
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            cmap = ds.colormap(1)
        for index, name in enumerate(["water", "vegetation"]):
            hex_value = CLASS_PALETTE[index].lstrip("#")
            r, g, b = (int(hex_value[i : i + 2], 16) for i in (0, 2, 4))
            assert cmap[index][:3] == (r, g, b), name

    def test_backend_and_frontend_palettes_identical(self):
        source = FRONTEND_PALETTE.read_text()
        block = re.search(r"CLASS_COLORS\s*=\s*\[(.*?)\]", source, re.S)
        assert block, "CLASS_COLORS not found in frontend palette"
        frontend = re.findall(r"'(#[0-9a-fA-F]{6})'", block.group(1))
        assert frontend == CLASS_PALETTE, (
            "frontend class colours drifted from the backend export palette"
        )

    def test_backend_and_frontend_uncertainty_ramp_identical(self):
        source = FRONTEND_OVERLAY.read_text()
        block = re.search(r"UNCERTAINTY_RAMP\s*=\s*\[(.*?)\]", source, re.S)
        assert block, "UNCERTAINTY_RAMP not found in frontend overlay"
        frontend = re.findall(r"'(#[0-9a-fA-F]{6})'", block.group(1))
        assert frontend == UNCERTAINTY_RAMP, (
            "frontend uncertainty ramp drifted from the export ramp"
        )

    def test_uncertainty_png_uses_ramp_endpoints(self, client, project, dataset, labeled):
        pytest.importorskip("PIL")
        from PIL import Image

        _train(client, project["id"])
        resp = client.get(
            f"/projects/{project['id']}/exports/uncertainty.png",
            params={"scale": 2, "method": "entropy"},
        )
        assert resp.status_code == 200
        image = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        colours = {px[:3] for px in image.getdata()}
        # every painted colour must lie on the shared ramp
        assert colours, "export is fully transparent"
        for colour in colours:
            assert colour in {ramp_color(i / 256) for i in range(257)}, colour

    def test_uncertainty_colours_stretch_over_the_field_range(self):
        field = np.array([[0.70, 0.80, 0.90, 1.00]], dtype=np.float32)
        rgb = uncertainty_colors(field)
        assert tuple(rgb[0, 0]) == ramp_color(0.0)  # coolest cell = min
        assert tuple(rgb[0, 3]) == ramp_color(1.0)  # warmest cell = max
        # strictly monotone toward warm across the row (warmth = red - blue;
        # the ramp's light midpoint means red alone is not monotone)
        warmth = [int(c[0]) - int(c[2]) for c in rgb[0]]
        assert warmth == sorted(warmth) and len(set(warmth)) == 4, warmth
        # a flat field is degenerate rather than a divide-by-zero
        flat = uncertainty_colors(np.full((2, 2), 0.9, dtype=np.float32))
        assert tuple(flat[1, 1]) == ramp_color(1.0)
        # NaN (invalid patch) stays unpainted
        assert np.all(uncertainty_colors(np.array([[np.nan]], dtype=np.float32)) == 0)

    def test_export_geometry_matches_patch_grid(self, client, project, dataset, labeled, geotiff_bytes):
        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/download/hard")
        with rasterio.open(io.BytesIO(resp.content)) as ds, rasterio.open(
            io.BytesIO(geotiff_bytes)
        ) as src:
            grid = json.loads(ds.tags()["grid"])
            # Patch cells are painted on the source grid, so the export keeps the
            # source dimensions/CRS/affine and every cell sits on its pixel window.
            assert (ds.height, ds.width) == (src.height, src.width)
            assert ds.crs == src.crs
            assert tuple(ds.transform)[:6] == pytest.approx(tuple(src.transform)[:6])
            assert ds.tags()["resolution"] == "patch-cells"
            values = ds.read(1)
            for cell in grid["cells"]:
                assert values[cell["y0"] : cell["y1"], cell["x0"] : cell["x1"]].min() == (
                    values[cell["y0"] : cell["y1"], cell["x0"] : cell["x1"]].max()
                )

    def test_clamped_edge_cells_are_not_misplaced(self, client, project, labeled):
        """A 70 px scene at 8 px patches: the last column/row is clamped."""
        rng = np.random.default_rng(11)
        h, w = 70, 70
        data = (rng.random((4, h, w)) * 200).astype(np.float32)
        buffer = io.BytesIO()
        with rasterio.open(
            buffer,
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
        ds = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": ("edge.tif", buffer.getvalue(), "image/tiff")},
        ).json()
        labels = []
        for row in range(9):
            for col in range(9):
                x, y = min(col * 8 + 4, w - 1), min(row * 8 + 4, h - 1)
                labels.append(
                    {
                        "geometry": {"type": "Point", "coordinates": [x, y]},
                        "class_name": "water" if col < 5 else "vegetation",
                        "dataset_id": ds["id"],
                    }
                )
        client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
        _train(client, project["id"])
        resp = client.get(
            f"/projects/{project['id']}/download/hard", params={"dataset_id": ds["id"]}
        )
        with rasterio.open(io.BytesIO(resp.content)) as gt:
            grid = json.loads(gt.tags()["grid"])
            # the grid covers the full extent, last cell clamped to the edge
            last = max(grid["cells"], key=lambda c: (c["row"], c["col"]))
            assert last["x1"] == w and last["y1"] == h
            assert grid["cells"][1]["x0"] - grid["cells"][0]["x0"] == 8

    def test_png_export_matches_class_palette(self, client, project, dataset, labeled):
        pytest.importorskip("PIL")
        from PIL import Image

        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/exports/hard.png", params={"scale": 4})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        image = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        assert image.size == (8 * 4, 8 * 4)
        colours = {px[:3] for px in image.getdata()}
        expected = {
            tuple(int(CLASS_PALETTE[i].lstrip("#")[j : j + 2], 16) for j in (0, 2, 4))
            for i in range(2)
        }
        assert colours <= expected, colours - expected

    def test_png_export_marks_invalid_cells_transparent(self, client, project, labeled):
        pytest.importorskip("PIL")
        from PIL import Image

        nodata = _nodata_dataset(client, project["id"])
        labels = [
            {
                "geometry": {"type": "Point", "coordinates": [col * 8 + 4, row * 8 + 4]},
                "class_name": "vegetation",
                "dataset_id": nodata["id"],
            }
            for row in range(8)
            for col in range(4, 8)
        ]
        client.post(f"/projects/{project['id']}/labels", json={"labels": labels})
        _train(client, project["id"])
        resp = client.get(
            f"/projects/{project['id']}/exports/uncertainty.png",
            params={"dataset_id": nodata["id"], "scale": 2},
        )
        image = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        pixels = list(image.getdata())
        transparent = [px for px in pixels if px[3] == 0]
        # 8 cells at scale 2 = 16x16 px; columns 0-3 are entirely nodata,
        # so the left 8 px of every row must be transparent.
        assert image.size == (16, 16)
        assert len(transparent) == 8 * 16
        for row in range(16):
            for col in range(16):
                alpha = pixels[row * 16 + col][3]
                assert (alpha == 0) == (col < 8), (row, col, alpha)

    def test_csv_export_rows(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(f"/projects/{project['id']}/exports/hard.csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(resp.content.decode())))
        assert len(rows) == 64
        assert rows[0]["row"] == "0" and rows[0]["col"] == "0"
        assert rows[0]["valid"] == "true"
        assert rows[0]["class_name"] in {"water", "vegetation"}
        assert float(rows[0]["uncertainty"]) >= 0.0
        assert rows[0]["x1"] == "8" and rows[0]["y1"] == "8"

    def test_csv_export_supports_uncertainty(self, client, project, dataset, labeled):
        _train(client, project["id"])
        resp = client.get(
            f"/projects/{project['id']}/exports/uncertainty.csv", params={"method": "margin"}
        )
        rows = list(csv.DictReader(io.StringIO(resp.content.decode())))
        assert len(rows) == 64
        assert {r["method"] for r in rows} == {"margin"}

    def test_png_and_csv_reject_probability(self, client, project, dataset, labeled):
        _train(client, project["id"])
        assert client.get(f"/projects/{project['id']}/exports/probability.png").status_code == 404
        assert client.get(f"/projects/{project['id']}/exports/probability.csv").status_code == 404


class TestPredictAugmentation:
    def test_predict_includes_uncertainty_and_validity(self, client, project, dataset, labeled):
        _train(client, project["id"])
        body = client.post(f"/projects/{project['id']}/predict", json={}).json()
        assert body["uncertainty_method"] == "entropy"
        assert np.shape(body["uncertainty_map"]) == (8, 8)
        assert np.shape(body["valid_map"]) == (8, 8)
        assert all(v is True for row in body["valid_map"] for v in row)
        assert "uncertainty" in body["exports"]

    def test_include_maps_false_omits_uncertainty(self, client, project, dataset, labeled):
        _train(client, project["id"])
        body = client.post(
            f"/projects/{project['id']}/predict", json={"include_maps": False}
        ).json()
        assert body["uncertainty_map"] is None


class TestClassLegend:
    def test_legend_matches_palette(self, client, project):
        resp = client.get(f"/projects/{project['id']}/legends/classes")
        assert resp.status_code == 200
        body = resp.json()["classes"]
        assert [c["name"] for c in body] == ["water", "vegetation"]
        assert [c["color"] for c in body] == CLASS_PALETTE[:2]
        assert [c["index"] for c in body] == [0, 1]
