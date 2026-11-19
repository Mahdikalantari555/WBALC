"""Pixel-area geometry for classified grids (Phase 4).

Two honest answers are possible, and they are not interchangeable:

- **Projected CRS with linear units** → pixel area is |det(affine)| converted to
  square metres. Exact, no approximation beyond the CRS itself.
- **Geographic CRS** → a degree rectangle is not a fixed area, so the area is
  integrated on the WGS84 ellipsoid per pixel row. This is exact for the
  ellipsoid, but it *assumes* the CRS is WGS84 rather than proving it — that
  assumption is reported with every result (`ellipsoid` field).

Nothing here guesses: an unsupported unit or an unknown CRS yields a method name
that says so, and the caller must not present a number.
"""

from __future__ import annotations

import math

import numpy as np
import rasterio

# WGS84 ellipsoid constants.
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)

# Metres per linear unit for projected CRSs. Unknown units are refused rather
# than assumed to be metres.
_LINEAR_TO_M = {
    "metre": 1.0,
    "meter": 1.0,
    "m": 1.0,
    "kilometre": 1000.0,
    "kilometer": 1000.0,
    "km": 1000.0,
    "foot": 0.3048,
    "us survey foot": 1200 / 3937,
    "us_survey_foot": 1200 / 3937,
    "feet": 0.3048,
}


def _ellipsoid_slab(sin_phi: float, e2: float = WGS84_E2) -> float:
    """Antiderivative of cos φ / (1 − e² sin²φ)² on the unit sphere's ellipsoid.

    Computed analytically so a lat/lon cell's area is exact on the ellipsoid
    rather than an `R²·Δφ·Δλ` approximation that would drift with latitude.
    """
    e = math.sqrt(e2)
    u = math.sin(sin_phi)
    denom = 1.0 - e2 * u * u
    return u / (2.0 * denom) + (1.0 / (4.0 * e)) * math.log((1.0 + e * u) / (1.0 - e * u))


def _geodesic_row_area(lat_top: float, lat_bottom: float, dlon_deg: float) -> float:
    """Exact WGS84 ellipsoid area (m²) of a lon/lat quad spanning two latitudes."""
    phi1 = math.radians(lat_bottom)
    phi2 = math.radians(lat_top)
    dlon = math.radians(dlon_deg)
    a2 = WGS84_A * WGS84_A * (1 - WGS84_E2)
    return abs(a2 * dlon * (_ellipsoid_slab(phi2) - _ellipsoid_slab(phi1)))


def crs_linear_unit(crs) -> str | None:
    """The CRS's linear unit name, or None when it cannot be read."""
    try:
        return crs.linear_units
    except Exception:  # noqa: BLE001 - older rasterio/GDAL builds lack it
        try:
            from rasterio.crs import CRS

            return CRS.from_wkt(crs.to_wkt()).linear_units
        except Exception:  # noqa: BLE001
            return None


def pixel_area_method(crs) -> dict:
    """Declare how pixel areas *can* be computed for this CRS, before doing it."""
    if crs is None:
        return {"kind": "unknown", "supported": False, "reason": "grid has no CRS"}
    if crs.is_projected:
        unit = crs_linear_unit(crs)
        factor = _LINEAR_TO_M.get((unit or "").strip().lower())
        if factor is None:
            return {
                "kind": "projected",
                "supported": False,
                "unit": unit,
                "reason": (
                    f"projected CRS linear unit '{unit}' is not one this build converts; "
                    "area is not reported rather than assumed to be metres"
                ),
            }
        return {"kind": "projected", "supported": True, "unit": unit, "metres_per_unit": factor}
    if crs.is_geographic:
        return {
            "kind": "geographic",
            "supported": True,
            "unit": "degrees",
            "ellipsoid": "WGS84 (assumed)",
            "note": (
                "pixel footprint area is integrated on the WGS84 ellipsoid per pixel row; "
                "the source CRS is treated as WGS84"
            ),
        }
    return {"kind": "other", "supported": False, "reason": f"unsupported CRS kind: {crs}"}


def pixel_areas(
    crs, transform: list[float] | tuple[float, ...], height: int, width: int
) -> tuple[np.ndarray, dict]:
    """Per-pixel areas in m², shaped (height, 1) so rows are broadcastable.

    A projected grid has one constant area; a geographic grid varies by row and
    is returned per row. Returning a column vector keeps both callers identical.
    """
    method = pixel_area_method(crs)
    if not method["supported"]:
        raise ValueError(method.get("reason", "pixel area is not computable for this grid"))

    a, b, c, d, e, f = [float(value) for value in transform]  # GDAL affine order
    if method["kind"] == "projected":
        det = abs(a * e - b * d)  # area in CRS units²
        square_metres = det * float(method["metres_per_unit"]) ** 2
        method.update(pixel_area_m2=square_metres, varies_by_row=False)
        return np.full((height, 1), square_metres, dtype=np.float64), method

    # Geographic: the affine maps pixel → (lon, lat); pixel height is |e| degrees.
    dlat = abs(e)
    dlon = abs(a)
    rows = np.empty((height, 1), dtype=np.float64)
    for row in range(height):
        # A pixel row spans [row, row+1] in pixel space: its top edge is at
        # `c + e*row`, its bottom edge one pixel lower. The longitude span of a
        # pixel is |a| (pixels are axis-aligned for these products).
        lat_top = f + e * row  # `f` is the y (latitude) origin of the raster
        lat_bottom = lat_top + e
        rows[row, 0] = _geodesic_row_area(min(lat_top, lat_bottom), max(lat_top, lat_bottom), dlon)
    method.update(
        pixel_area_m2=float(rows.mean()),
        varies_by_row=True,
        row_area_min_m2=float(rows.min()),
        row_area_max_m2=float(rows.max()),
    )
    return rows, method


def area_by_class(
    hard: np.ndarray,
    valid: np.ndarray,
    classes: list[str],
    areas: np.ndarray,
    *,
    nodata: int | None = None,
) -> dict:
    """Area per class over *valid* pixels only, with its denominators.

    Invalid pixels are excluded from both the numerator and the denominator, and
    the coverage that remains is reported so a small map cannot look complete.
    """
    grid = np.asarray(hard)
    mask = np.asarray(valid, dtype=bool)
    if nodata is not None:
        mask = mask & (grid != nodata)
    area_array = np.asarray(areas, dtype=np.float64)
    if area_array.shape == grid.shape:
        # Per-cell areas (patch grids): the mean is the honest single number.
        row_areas = area_array
    else:
        row_areas = area_array.reshape(-1, 1)
    total_pixels = int(grid.size)
    valid_pixels = int(mask.sum())
    coverage = (valid_pixels / total_pixels) if total_pixels else 0.0

    per_class = []
    for index, name in enumerate(classes):
        selected = mask & (grid == index)
        pixel_count = int(selected.sum())
        square_metres = float((selected * row_areas).sum())
        per_class.append(
            {
                "class_index": index,
                "class_name": name,
                "valid_pixels": pixel_count,
                "area_m2": square_metres,
                "area_ha": square_metres / 10_000.0,
                "share_of_valid": (pixel_count / valid_pixels) if valid_pixels else 0.0,
            }
        )

    return {
        "per_class": per_class,
        "valid_pixels": valid_pixels,
        "invalid_pixels": total_pixels - valid_pixels,
        "total_pixels": total_pixels,
        "coverage": coverage,
        "valid_area_m2": float((mask * row_areas).sum()),
        "valid_area_ha": float((mask * row_areas).sum()) / 10_000.0,
        "pixel_area_m2_mean": float(np.mean(row_areas)),
    }


def transitions(
    before: np.ndarray,
    after: np.ndarray,
    valid_before: np.ndarray,
    valid_after: np.ndarray,
    classes: list[str],
    areas: np.ndarray,
    *,
    nodata: int | None = None,
) -> dict:
    """Class-transition counts and areas over the jointly valid footprint.

    Only pixels valid in *both* dates are counted; "valid denominator" is that
    intersection, so a change map cannot be inflated by shifting cloud masks.
    """
    first = np.asarray(before)
    second = np.asarray(after)
    joint = np.asarray(valid_before, dtype=bool) & np.asarray(valid_after, dtype=bool)
    if nodata is not None:
        joint = joint & (first != nodata) & (second != nodata)
    if first.shape != second.shape:
        raise ValueError(
            f"grids differ in shape ({first.shape} vs {second.shape}); alignment must be explicit"
        )
    area_array = np.asarray(areas, dtype=np.float64)
    row_areas = area_array if area_array.shape == first.shape else area_array.reshape(-1, 1)
    n = len(classes)
    matrix = np.zeros((n, n), dtype=np.int64)
    matrix_area = np.zeros((n, n), dtype=np.float64)
    ys, xs = np.nonzero(joint)
    for y, x in zip(ys, xs):
        a = int(first[y, x])
        b = int(second[y, x])
        if 0 <= a < n and 0 <= b < n:
            matrix[a, b] += 1
            matrix_area[a, b] += float(
                row_areas[y, x] if row_areas.shape == first.shape else row_areas[y, 0]
            )

    joint_pixels = int(joint.sum())
    changed = int(matrix.sum() - np.trace(matrix))
    changes = []
    for a in range(n):
        for b in range(n):
            if a != b and matrix[a, b]:
                changes.append(
                    {
                        "from": classes[a],
                        "to": classes[b],
                        "pixels": int(matrix[a, b]),
                        "area_m2": float(matrix_area[a, b]),
                        "area_ha": float(matrix_area[a, b]) / 10_000.0,
                    }
                )
    changes.sort(key=lambda row: row["pixels"], reverse=True)
    return {
        "classes": classes,
        "matrix": matrix.tolist(),
        "matrix_area_m2": matrix_area.tolist(),
        "joint_valid_pixels": joint_pixels,
        "changed_pixels": changed,
        "changed_area_m2": float(matrix_area.sum() - np.trace(matrix_area)),
        "changed_area_ha": float(matrix_area.sum() - np.trace(matrix_area)) / 10_000.0,
        "unchanged_pixels": int(np.trace(matrix)),
        "joint_valid_area_m2": float(matrix_area.sum()),
        "joint_valid_area_ha": float(matrix_area.sum()) / 10_000.0,
        "changes": changes,
        "denominator": "pixels valid in both dates",
    }


def water_areas(area_summary: dict, water_classes: list[str]) -> dict:
    """Binary water total, computed only from classes the taxonomy calls water."""
    water = [
        entry for entry in area_summary["per_class"] if entry["class_name"] in water_classes
    ]
    square_metres = sum(entry["area_m2"] for entry in water)
    return {
        "water_classes": water_classes,
        "area_m2": square_metres,
        "area_ha": square_metres / 10_000.0,
        "valid_area_m2": area_summary["valid_area_m2"],
        "share_of_valid": (
            square_metres / area_summary["valid_area_m2"]
            if area_summary["valid_area_m2"]
            else 0.0
        ),
    }
