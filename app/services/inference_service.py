"""Patch-grid inference and GeoTIFF export.

Two products share this module:

- **Pixel mode** — one class/probability/uncertainty value per source pixel,
  written on the source affine translated by the region origin.
- **Patch mode** — one value per patch cell. A GeoTIFF can only carry one affine,
  and the patch grid clamps its last row/column, so cells are painted over their
  *true* pixel windows on the source grid (nearest-neighbour block fill, never
  interpolated). The `grid` tag records the exact window of every cell; pixels
  covered by no cell (only possible when ``stride > patch_size``) stay nodata.

Every writer goes through :func:`_atomic_write`, so an interrupted export never
leaves a half-written file at the published path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.windows import Window

from .al_service import uncertainty_scores
from .raster_service import PatchGrid, transform_of

NODATA = 65535
PROBABILITY_NODATA = -9999.0
UNCERTAINTY_NODATA = -9999.0

# Single source of truth for class colours. The workspace mirrors this list in
# `frontend/src/lib/palette.ts` (a test asserts they are identical), so a class
# is the same colour on screen and in an exported GeoTIFF.
CLASS_PALETTE: list[str] = [
    "#5cbb96",
    "#e0a458",
    "#7d9bd4",
    "#c97b9b",
    "#9b8cd4",
    "#d4c95c",
    "#6bb8c9",
    "#d47b6b",
    "#8bc96b",
    "#b0b7c3",
    "#c9a0dc",
]


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


# Cool (confident) -> warm (uncertain). The workspace mirrors this ramp in
# `frontend/src/lib/overlay.ts`; a test asserts the two stay identical, so an
# exported uncertainty PNG is the same picture the map shows.
UNCERTAINTY_RAMP: list[str] = ["#3c78c8", "#f0e6a8", "#e0663c"]


def ramp_color(t: float, ramp: list[str] | None = None) -> tuple[int, int, int]:
    """Colour at position `t` (clamped to 0..1) along a multi-stop hex ramp."""
    stops = [hex_to_rgb(c) for c in (ramp or UNCERTAINTY_RAMP)]
    t = min(1.0, max(0.0, float(t)))
    scaled = t * (len(stops) - 1)
    index = min(len(stops) - 2, int(scaled))
    local = scaled - index
    return tuple(  # type: ignore[return-value]
        round(stops[index][i] + (stops[index + 1][i] - stops[index][i]) * local) for i in range(3)
    )


def uncertainty_colors(values: np.ndarray) -> np.ndarray:
    """[rows, cols] uncertainty -> [rows, cols, 3] uint8, stretched over the
    field's own finite range (a trained model's entropy rarely spans 0..1)."""
    finite = values[np.isfinite(values)]
    lo = float(finite.min()) if finite.size else 0.0
    hi = float(finite.max()) if finite.size else 1.0
    span = hi - lo
    out = np.zeros((*values.shape, 3), dtype=np.uint8)
    for r in range(values.shape[0]):
        for c in range(values.shape[1]):
            value = float(values[r, c])
            if not np.isfinite(value):
                continue
            t = (value - lo) / span if span > 0 else 1.0
            out[r, c] = ramp_color(t)
    return out


def class_colors(n: int) -> list[tuple[int, int, int]]:
    """RGB for class indices 0..n-1, cycling the shared palette."""
    if n <= 0:
        return []
    return [hex_to_rgb(CLASS_PALETTE[i % len(CLASS_PALETTE)]) for i in range(n)]


def predict_patches(model, X: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict_proba(X), dtype=np.float64)


def maps_from_probabilities(
    probs: np.ndarray, grid_shape: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    """Return (hard_map [rows, cols] of class indices, prob_map [classes, rows, cols])."""
    rows, cols = grid_shape
    hard = np.argmax(probs, axis=1).reshape(rows, cols).astype(np.uint16)
    prob = probs.T.reshape(probs.shape[1], rows, cols).astype(np.float32)
    return hard, prob


def uncertainty_map(prob: np.ndarray, method: str = "entropy") -> np.ndarray:
    """Per-cell uncertainty, [rows, cols] float32, from [classes, rows, cols] probs.

    Uses the same maths as the active-learning ranking, so the map cannot
    disagree with the batch it explains.
    """
    k, rows, cols = prob.shape
    flat = np.moveaxis(prob, 0, 1).reshape(rows * cols, k).astype(np.float64)
    if flat.shape[0] == 0:
        return np.zeros((rows, cols), dtype=np.float32)
    return uncertainty_scores(flat, method).reshape(rows, cols).astype(np.float32)


def maps_from_inference(
    probs: np.ndarray,
    valid: np.ndarray,
    grid_shape: tuple[int, int],
    method: str = "entropy",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(hard, prob, uncertainty) with every output masked at invalid cells.

    The three outputs must agree: a cell the response calls invalid cannot carry
    a class, a probability vector or an uncertainty value. Previously only the
    hard map (sentinel) and the uncertainty map (NaN) were masked, so callers
    that trusted probabilities saw a confident distribution for nodata ground.
    """
    hard, prob = maps_from_probabilities(probs, grid_shape)
    unc = uncertainty_map(prob, method)
    invalid = ~valid.reshape(grid_shape)
    hard = hard.copy()
    hard[invalid] = NODATA
    prob = prob.copy()
    prob[:, invalid] = np.nan
    unc[invalid] = np.nan
    return hard, prob, unc


def grid_lattice(
    base_transform: list[float] | None,
    step: int,
    region_x0: int,
    region_y0: int,
) -> Affine:
    """Transform of the uniform `step`-pixel lattice the grid cells are written on.

    The backend clamps the last grid row/column to the image edge, so cells are
    not uniformly spaced. A GeoTIFF can only carry one affine, so exports use the
    regular stride lattice and pad the cells the grid does not cover with nodata;
    the true per-cell windows travel in the `grid` tag. That keeps cell (row, col)
    on the same ground the map draws.
    """
    base = transform_of(base_transform)
    return base @ Affine.translation(region_x0, region_y0) @ Affine.scale(step, step)


def grid_transform(
    base_transform: list[float] | None,
    grid: PatchGrid,
    region_x0: int,
    region_y0: int,
    stride: int,
) -> Affine:
    """Kept for callers that only need the lattice; see :func:`grid_lattice`."""
    return grid_lattice(base_transform, max(1, stride), region_x0, region_y0)


def grid_metadata(
    grid: PatchGrid,
    region_x0: int,
    region_y0: int,
    stride: int,
    include_cells: bool = True,
) -> dict:
    """Per-cell pixel windows + grid info, attachable to a GeoTIFF or JSON.

    ``include_cells=False`` is used for pixel-mode rasters, where every pixel is
    its own cell: enumerating them would embed millions of dictionaries in a tag
    (and in the response) without adding information.
    """
    rows, cols = grid.shape
    if not include_cells:
        return {
            "rows": rows,
            "cols": cols,
            "patch_size": 1,
            "stride": 1,
            "region": {"x0": region_x0, "y0": region_y0},
            "cells_are_pixels": True,
        }
    cells = [
        {
            "row": r,
            "col": c,
            "x0": grid.xs[c] + region_x0,
            "y0": grid.ys[r] + region_y0,
            "x1": grid.xs[c] + region_x0 + grid.patch_w,
            "y1": grid.ys[r] + region_y0 + grid.patch_h,
        }
        for r in range(rows)
        for c in range(cols)
    ]
    return {
        "rows": rows,
        "cols": cols,
        "patch_size": grid.patch_w if grid.patch_w == grid.patch_h else [grid.patch_h, grid.patch_w],
        "stride": stride,
        "region": {"x0": region_x0, "y0": region_y0},
        "cells": cells,
    }


def pixel_transform(
    base_transform: list[float] | None,
    region_x0: int,
    region_y0: int,
) -> Affine:
    """Exact pixel-level affine transform for a cropped raster region."""
    return transform_of(base_transform) @ Affine.translation(region_x0, region_y0)


def _atomic_write(path: str | Path, write) -> None:
    """Run ``write(tmp_path)`` and publish it with an atomic rename.

    A crash, a full disk or a validation error must never leave a partially
    written GeoTIFF where a download endpoint can serve it.
    """
    final = Path(path)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        write(tmp)
        os.replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _base_tags(classes: list[str], grid: dict | None, resolution: str | None) -> dict:
    tags = {"classes": json.dumps(classes)}
    if grid is not None:
        tags["grid"] = json.dumps(grid)
    if resolution is not None:
        tags["resolution"] = resolution
    return tags


def _cell_windows(grid: PatchGrid, rows: int, cols: int):
    """Yield (row, col, y0, x0, height, width) using the grid's true windows."""
    for r in range(rows):
        y0, h = grid.ys[r], grid.patch_h
        for c in range(cols):
            yield r, c, y0, grid.xs[c], h, grid.patch_w


def export_som_geotiff(
    path: str | Path,
    cluster_map: np.ndarray,
    cluster_labels: list[str],
    colors: list[tuple[int, int, int]],
    crs: str | None,
    transform: Affine,
    grid: dict | None = None,
    resolution: str = "pixel",
) -> None:
    """Write an unsupervised SOM classification GeoTIFF with embedded colormap."""

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=cluster_map.shape[0],
            width=cluster_map.shape[1],
            count=1,
            dtype="uint16",
            crs=crs,
            transform=transform,
            nodata=NODATA,
            compress="deflate",
        ) as dst:
            dst.write(cluster_map.astype(np.uint16), 1)
            dst.update_tags(
                **_base_tags(cluster_labels, grid, resolution),
                description=(
                    "RSAL unsupervised SOM classification map "
                    "(pixel value = 0-based cluster index)"
                ),
            )
            dst.write_colormap(
                1,
                {i: (int(c[0]), int(c[1]), int(c[2]), 255) for i, c in enumerate(colors)},
            )

    _atomic_write(path, _write)


def export_hard_geotiff(
    path: str | Path,
    hard: np.ndarray,
    classes: list[str],
    crs: str | None,
    transform: Affine,
    grid: dict | None = None,
    resolution: str | None = None,
) -> None:
    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=hard.shape[0],
            width=hard.shape[1],
            count=1,
            dtype="uint16",
            crs=crs,
            transform=transform,
            nodata=NODATA,
            compress="deflate",
        ) as dst:
            dst.write(hard.astype(np.uint16), 1)
            dst.update_tags(
                **_base_tags(classes, grid, resolution),
                description=(
                    "RSAL hard classification map (pixel value = 0-based index into classes)"
                ),
            )
            dst.write_colormap(
                1, {i: (*class_colors(len(classes))[i], 255) for i in range(len(classes))}
            )

    _atomic_write(path, _write)


def export_uncertainty_geotiff(
    path: str | Path,
    unc: np.ndarray,
    classes: list[str],
    crs: str | None,
    transform: Affine,
    method: str,
    grid: dict | None = None,
    resolution: str | None = None,
) -> None:
    data = np.nan_to_num(unc, nan=UNCERTAINTY_NODATA).astype(np.float32)

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=UNCERTAINTY_NODATA,
            compress="deflate",
        ) as dst:
            dst.write(data, 1)
            dst.update_tags(
                **_base_tags(classes, grid, resolution),
                method=method,
                description=(
                    "RSAL uncertainty map, 0 (confident) .. 1 (uncertain); "
                    "nodata marks cells with no valid source pixels"
                ),
            )
            dst.set_band_description(1, method)

    _atomic_write(path, _write)


def export_probability_geotiff(
    path: str | Path,
    prob: np.ndarray,
    classes: list[str],
    crs: str | None,
    transform: Affine,
    grid: dict | None = None,
    valid: np.ndarray | None = None,
    resolution: str | None = None,
) -> None:
    k, h, w = prob.shape
    data = prob.astype(np.float32, copy=True)
    data[~np.isfinite(data)] = PROBABILITY_NODATA
    if valid is not None:
        if valid.size != h * w:
            raise ValueError("Probability validity mask shape does not match output grid")
        data[:, ~valid.reshape(h, w)] = PROBABILITY_NODATA

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=k,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=PROBABILITY_NODATA,
            compress="deflate",
        ) as dst:
            dst.write(data)
            for i, name in enumerate(classes):
                dst.set_band_description(i + 1, name)
            dst.update_tags(
                **_base_tags(classes, grid, resolution),
                description=(
                    "RSAL per-class probability map; nodata marks cells with no "
                    "valid source pixels"
                ),
            )

    _atomic_write(path, _write)


# ------------------------------------------------- patch cells -> source grid
def export_hard_cells_geotiff(
    path: str | Path,
    hard: np.ndarray,
    valid: np.ndarray,
    grid: PatchGrid,
    classes: list[str],
    crs: str | None,
    transform: Affine,
    height: int,
    width: int,
    grid_meta: dict | None = None,
    resolution: str = "patch-cells",
) -> None:
    """Paint per-cell class indices over their true pixel windows.

    The output has the source region's dimensions and affine, so a consumer that
    ignores the ``grid`` tag still sees every cell on the ground it describes.
    """
    rows, cols = hard.shape
    windows = list(_cell_windows(grid, rows, cols))

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="uint16",
            crs=crs,
            transform=transform,
            nodata=NODATA,
            compress="deflate",
        ) as dst:
            for r in range(rows):
                y0, cell_h = grid.ys[r], grid.patch_h
                block = np.full((cell_h, width), NODATA, dtype=np.uint16)
                for row_idx, col_idx, _y, x0, _h, cell_w in windows:
                    if row_idx != r:
                        continue
                    if not valid[row_idx, col_idx]:
                        continue
                    block[:, x0 : x0 + cell_w] = hard[row_idx, col_idx]
                dst.write(block, 1, window=Window(0, y0, width, cell_h))
            dst.update_tags(
                **_base_tags(classes, grid_meta, resolution),
                description=(
                    "RSAL patch-cell classification map: each cell's class is "
                    "replicated over its true pixel window (nearest neighbour, "
                    "never interpolated); see the grid tag for cell windows"
                ),
            )
            dst.write_colormap(
                1, {i: (*class_colors(len(classes))[i], 255) for i in range(len(classes))}
            )

    _atomic_write(path, _write)


def export_uncertainty_cells_geotiff(
    path: str | Path,
    unc: np.ndarray,
    valid: np.ndarray,
    grid: PatchGrid,
    classes: list[str],
    crs: str | None,
    transform: Affine,
    method: str,
    height: int,
    width: int,
    grid_meta: dict | None = None,
    resolution: str = "patch-cells",
) -> None:
    rows, cols = unc.shape
    windows = list(_cell_windows(grid, rows, cols))
    masked = np.where(np.isfinite(unc), unc, np.nan)

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=UNCERTAINTY_NODATA,
            compress="deflate",
        ) as dst:
            for r in range(rows):
                y0, cell_h = grid.ys[r], grid.patch_h
                block = np.full((cell_h, width), UNCERTAINTY_NODATA, dtype=np.float32)
                for row_idx, col_idx, _y, x0, _h, cell_w in windows:
                    if row_idx != r or not valid[row_idx, col_idx]:
                        continue
                    value = masked[row_idx, col_idx]
                    if not np.isfinite(value):
                        continue
                    block[:, x0 : x0 + cell_w] = np.float32(value)
                dst.write(block, 1, window=Window(0, y0, width, cell_h))
            dst.update_tags(
                **_base_tags(classes, grid_meta, resolution),
                method=method,
                description=(
                    "RSAL patch-cell uncertainty map, 0 (confident) .. 1 "
                    "(uncertain); nodata marks cells without valid pixels"
                ),
            )
            dst.set_band_description(1, method)

    _atomic_write(path, _write)


def export_probability_cells_geotiff(
    path: str | Path,
    prob: np.ndarray,
    valid: np.ndarray,
    grid: PatchGrid,
    classes: list[str],
    crs: str | None,
    transform: Affine,
    height: int,
    width: int,
    grid_meta: dict | None = None,
    resolution: str = "patch-cells",
) -> None:
    """One band per class, written cell-row by cell-row to bound memory."""
    k, rows, cols = prob.shape
    windows = list(_cell_windows(grid, rows, cols))

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=k,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=PROBABILITY_NODATA,
            compress="deflate",
        ) as dst:
            for r in range(rows):
                y0, cell_h = grid.ys[r], grid.patch_h
                block = np.full((k, cell_h, width), PROBABILITY_NODATA, dtype=np.float32)
                for row_idx, col_idx, _y, x0, _h, cell_w in windows:
                    if row_idx != r or not valid[row_idx, col_idx]:
                        continue
                    block[:, :, x0 : x0 + cell_w] = prob[:, row_idx, col_idx][
                        :, None, None
                    ]
                dst.write(block, window=Window(0, y0, width, cell_h))
            for i, name in enumerate(classes):
                dst.set_band_description(i + 1, name)
            dst.update_tags(
                **_base_tags(classes, grid_meta, resolution),
                description=(
                    "RSAL patch-cell per-class probability map; nodata marks "
                    "cells without valid pixels"
                ),
            )

    _atomic_write(path, _write)


def rasterize_cells(
    values: np.ndarray,
    valid: np.ndarray,
    grid: PatchGrid,
    height: int,
    width: int,
    fill: int = NODATA,
) -> np.ndarray:
    """Block-fill per-cell values onto the source grid (nearest neighbour).

    Used by the SOM export and available to any caller that needs a cell map in
    the source grid's geometry. Never interpolates: a cell's value is copied
    verbatim over its window, so categorical data stays categorical.
    """
    rows, cols = values.shape
    out = np.full((height, width), fill, dtype=values.dtype)
    for r in range(rows):
        y0, cell_h = grid.ys[r], grid.patch_h
        for c in range(cols):
            if not valid[r, c]:
                continue
            x0, cell_w = grid.xs[c], grid.patch_w
            out[y0 : y0 + cell_h, x0 : x0 + cell_w] = values[r, c]
    return out


def validate_export_grid(
    reference_path: str | Path,
    candidate_paths,
    window: tuple[int, int, int, int],
) -> None:
    """Reopen written exports and compare them with the expected source window.

    Raises :class:`RasterError` (from ``validate_grid_compatibility``) on any
    mismatch; callers delete the artifacts and fail the request.
    """
    from .raster_service import validate_grid_compatibility

    with rasterio.open(reference_path) as reference:
        for candidate_path in candidate_paths:
            with rasterio.open(candidate_path) as candidate:
                validate_grid_compatibility(reference, candidate, window=window)
