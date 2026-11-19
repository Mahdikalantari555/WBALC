"""Project study-area masking for predictions.

The study area is vector geometry in a project CRS; the raster is in its own
CRS. Getting from one to the other is a *vector* coordinate transformation —
never a raster reprojection or resampling — and it is allowed to fail loudly.

Implementation notes:

- Only `Polygon` and `MultiPolygon` geometries constrain anything. Points and
  lines have no interior, so they are rejected rather than treated as "inside
  everything".
- Pixel centres are tested with a scanline fill in pixel space. That is exact for
  axis-aligned affine transforms (the normal GeoTIFF case) and avoids a heavy
  geometry dependency in the request path.
- No CRS, no transformation, or a non-invertible transform raises `StudyAreaError`
  so the caller can return a clear 4xx instead of publishing an unmasked product.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from affine import Affine
from rasterio.warp import transform as transform_coordinates


class StudyAreaError(ValueError):
    """The study area cannot be applied to this raster."""


def _rings(geometry: dict[str, Any]) -> tuple[list[list[list[float]]], list[list[list[list[float]]]]]:
    """Split a Polygon/MultiPolygon GeoJSON into (outer rings, holes per polygon)."""
    kind = geometry.get("type")
    if kind == "Polygon":
        coordinates = geometry.get("coordinates") or []
        if not coordinates:
            raise StudyAreaError("Study-area polygon has no rings")
        return [coordinates[0]], [coordinates[1:]]
    if kind == "MultiPolygon":
        outers, holes = [], []
        for polygon in geometry.get("coordinates") or []:
            if not polygon:
                raise StudyAreaError("Study-area multipolygon contains an empty polygon")
            outers.append(polygon[0])
            holes.append(polygon[1:])
        if not outers:
            raise StudyAreaError("Study-area multipolygon has no polygons")
        return outers, holes
    raise StudyAreaError(
        f"Study-area geometry type '{kind}' cannot mask pixels; "
        "use a Polygon or MultiPolygon"
    )


def _transform_rings(
    rings: list[list[list[float]]], source_crs: str | None, target_crs: str | None
) -> list[list[tuple[float, float]]]:
    if not source_crs or not target_crs:
        raise StudyAreaError(
            "Study-area masking needs both the project CRS and the raster CRS; "
            f"project='{source_crs}', raster='{target_crs}'"
        )
    flat = [point for ring in rings for point in ring]
    if not flat:
        raise StudyAreaError("Study-area geometry has no coordinates")
    xs = [float(point[0]) for point in flat]
    ys = [float(point[1]) for point in flat]
    try:
        if source_crs == target_crs:
            out_x, out_y = xs, ys
        else:
            out_x, out_y = transform_coordinates(source_crs, target_crs, xs, ys)
    except Exception as exc:  # rasterio raises its own error types
        raise StudyAreaError(
            f"Could not transform the study area from {source_crs} to {target_crs}: {exc}"
        ) from exc
    if not all(np.isfinite(out_x)) or not all(np.isfinite(out_y)):
        raise StudyAreaError("Study-area coordinates are not finite after CRS transformation")
    cursor = 0
    transformed = []
    for ring in rings:
        size = len(ring)
        transformed.append(list(zip(out_x[cursor : cursor + size], out_y[cursor : cursor + size])))
        cursor += size
    return transformed


def _to_pixel(rings: list[list[tuple[float, float]]], transform: Affine) -> list[np.ndarray]:
    try:
        inverse = ~transform
    except Exception as exc:  # affine raises for a singular matrix
        raise StudyAreaError(f"Raster affine transform is not invertible: {exc}") from exc
    if not np.isfinite(inverse.a * inverse.e - inverse.b * inverse.d) or (
        abs(inverse.a * inverse.e - inverse.b * inverse.d) < 1e-18
    ):
        raise StudyAreaError("Raster affine transform is degenerate; cannot locate the study area")
    out = []
    for ring in rings:
        xs = np.array([point[0] for point in ring], dtype=float)
        ys = np.array([point[1] for point in ring], dtype=float)
        cols, rows = inverse * (xs, ys)
        out.append(np.column_stack([np.asarray(cols), np.asarray(rows)]))
    return out


def _scanline_fill(polygons: list[tuple[np.ndarray, list[np.ndarray]]], height: int, width: int) -> np.ndarray:
    """Even-odd fill at pixel centres (row + 0.5, col + 0.5), holes respected."""
    mask = np.zeros((height, width), dtype=bool)
    row_centres = np.arange(height) + 0.5
    col_centres = np.arange(width) + 0.5
    for outer, holes in polygons:
        rings = [outer, *holes]
        xs_all = [ring[:, 0] for ring in rings]
        rows_all = [ring[:, 1] for ring in rings]
        min_row = max(0, int(np.floor(min(float(r.min()) for r in rows_all))))
        max_row = min(height - 1, int(np.ceil(max(float(r.max()) for r in rows_all))))
        min_col = max(0, int(np.floor(min(float(x.min()) for x in xs_all))))
        max_col = min(width - 1, int(np.ceil(max(float(x.max()) for x in xs_all))))
        if min_row > max_row or min_col > max_col:
            continue
        crossing_rows = row_centres[min_row : max_row + 1]
        inside = np.zeros((len(crossing_rows), width), dtype=bool)
        for ring in rings:
            x0, y0 = ring[:, 0], ring[:, 1]
            x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
            for j, row in enumerate(crossing_rows):
                straddles = (y0 <= row) != (y1 <= row)
                if not straddles.any():
                    continue
                with np.errstate(divide="ignore", invalid="ignore"):
                    crossings = x0[straddles] + (row - y0[straddles]) * (
                        (x1[straddles] - x0[straddles]) / (y1[straddles] - y0[straddles])
                    )
                crossings = np.sort(crossings[np.isfinite(crossings)])
                if crossings.size < 2:
                    continue
                for start, stop in zip(crossings[0::2], crossings[1::2]):
                    inside[j] |= (col_centres >= start) & (col_centres < stop)
        mask[min_row : max_row + 1, :] |= inside
        del min_col, max_col  # bounds kept for readability of the row window
    return mask


def study_area_mask(
    geometry: dict[str, Any] | None,
    project_crs: str | None,
    raster_crs: str | None,
    transform: list[float] | None,
    *,
    region: tuple[int, int, int, int] = (0, 0, 0, 0),
    height: int,
    width: int,
    shape: tuple[int, int],
) -> tuple[np.ndarray, str]:
    """Boolean pixel-centre mask for one prediction window.

    ``region`` is ``(x0, y0, width, height)`` in the raster's pixel space and
    ``shape`` is the shape of the *returned* grid (patch-cell grid or pixel grid),
    which is what the mask has to match.
    """
    if not geometry:
        return np.ones(shape, dtype=bool), "no study area configured"
    x0, y0 = region[0], region[1]
    if not transform:
        raise StudyAreaError(
            "Study area is configured but the raster has no affine transform, "
            "so pixel centres cannot be located"
        )
    transform = [float(v) for v in transform]
    raster_affine = Affine(*transform[:6])
    window_affine = raster_affine * Affine.translation(x0, y0)

    outers, holes = _rings(geometry)
    transformed_outers = _transform_rings(outers, project_crs, raster_crs)
    # A hole-free polygon still arrives as `[[]]`; empty groups mean "no holes",
    # not "a ring with no coordinates".
    transformed_holes = [
        _transform_rings(group, project_crs, raster_crs) if group else [] for group in holes
    ]

    polygons: list[tuple[np.ndarray, list[np.ndarray]]] = []
    for index, outer in enumerate(transformed_outers):
        pixel_outer = _to_pixel([outer], window_affine)[0]
        pixel_holes = [
            _to_pixel([hole], window_affine)[0] for hole in transformed_holes[index] if hole
        ]
        polygons.append((pixel_outer, pixel_holes))

    # At pixel resolution the mask is per source pixel; for patch cells a cell is
    # inside when its centre is inside, because a cell is a single prediction.
    full = _scanline_fill(polygons, height, width)
    if shape == (height, width):
        return full, "study area applied"
    rows, cols = shape
    row_index = np.minimum((np.arange(rows) + 0.5) * (height / rows), height - 1).astype(int)
    col_index = np.minimum((np.arange(cols) + 0.5) * (width / cols), width - 1).astype(int)
    return full[np.ix_(row_index, col_index)], "study area applied at patch-cell resolution"
