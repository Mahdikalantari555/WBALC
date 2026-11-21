"""Model-free water detection by Otsu thresholding.

A research product, not a classification: one spectral or SAR index, one
threshold chosen by Otsu on the scene's own valid pixels, one binary mask.
Everything is computed on the scene's native grid with its own nodata and
study-area rules, so the mask can be compared against the raw scene without
any resampling step in between.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

# Normalized-difference water indices: (name, first band, second band).
# Water is where (first - second) / (first + second) is ABOVE the threshold.
SPECTRAL_WATER_INDICES: dict[str, tuple[str, str]] = {
    "ndwi": ("green", "nir08"),
    "mndwi": ("green", "swir16"),
}

# SAR water indices: open water dampens backscatter, so water is where the
# band value is BELOW the threshold.
SAR_WATER_INDICES: tuple[str, ...] = ("vv", "vh")

BAND_ALIASES: dict[str, tuple[str, ...]] = {
    "green": ("green", "b03", "b3"),
    "nir08": ("nir", "nir08", "nir_08", "b08", "b8"),
    "swir16": ("swir16", "swir_16", "b11", "b11"),
    "vv": ("vv",),
    "vh": ("vh",),
}

AUTO_INDEX_BY_SENSOR = {"Sentinel-2": "ndwi", "Sentinel-1": "vv"}


class WaterThresholdError(Exception):
    """The scene cannot support the requested water index."""


@dataclass(frozen=True)
class WaterThresholdResult:
    index: str
    bands: tuple[str, ...]
    direction: str  # 'above' (spectral) or 'below' (SAR)
    threshold: float
    method: str
    values: np.ndarray  # int8, -1 marks invalid
    valid: np.ndarray  # bool
    counts: dict
    areas: dict
    grid: dict


def resolve_index(sensor: str | None, requested: str | None) -> str:
    """Pick the default index for a sensor or validate an explicit request."""
    known = set(SPECTRAL_WATER_INDICES) | set(SAR_WATER_INDICES)
    if requested is None or requested == "auto":
        if sensor in AUTO_INDEX_BY_SENSOR:
            return AUTO_INDEX_BY_SENSOR[sensor]
        raise WaterThresholdError(
            "Scene sensor is unknown, so no default water index applies; "
            "request one of ndwi, mndwi, vv, vh explicitly"
        )
    if requested not in known:
        raise WaterThresholdError(
            f"Unknown water index '{requested}'; use one of {sorted(known)}"
        )
    return requested


def _band_position(band_names: list[str | None], canonical: str) -> int:
    aliases = BAND_ALIASES.get(canonical, (canonical,))
    for position, name in enumerate(band_names):
        if name and name.strip().lower() in aliases:
            return position
    raise WaterThresholdError(
        f"This scene has no '{canonical}' band (registered bands: "
        f"{[name for name in band_names if name]}), so the requested water "
        "index cannot be computed"
    )


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    """Classic Otsu on a 1-D array of finite values (histogram based)."""
    if values.size == 0:
        raise WaterThresholdError("No valid pixels available for the water threshold")
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return low
    histogram, edges = np.histogram(values, bins=bins, range=(low, high))
    centers = (edges[:-1] + edges[1:]) / 2.0
    weight_left = np.cumsum(histogram).astype(float)
    weight_right = weight_left[-1] - weight_left
    weighted = np.cumsum(histogram * centers)
    mean_left = weighted / np.maximum(weight_left, 1e-12)
    mean_right = (weighted[-1] - weighted) / np.maximum(weight_right, 1e-12)
    between = weight_left * weight_right * (mean_left - mean_right) ** 2
    split = int(np.argmax(between))
    # Midpoint of the two class means: for edge-pinned bimodal data the optimal
    # plateau spans many bins, and the class-mean midpoint stays at the true
    # separation while a raw bin centre would hug one mode.
    return float((mean_left[split] + mean_right[split]) / 2.0)


def compute_water_threshold(
    raster_path: Path | str,
    index: str,
    band_names: list[str | None],
    nodata_values: list[float | None] | None,
    study_area: np.ndarray | None = None,
) -> WaterThresholdResult:
    """Compute the binary water mask for one scene on its native grid."""
    if index in SPECTRAL_WATER_INDICES:
        first_name, second_name = SPECTRAL_WATER_INDICES[index]
        positions = [_band_position(band_names, first_name), _band_position(band_names, second_name)]
        direction = "above"
        bands = (first_name, second_name)
    elif index in SAR_WATER_INDICES:
        positions = [_band_position(band_names, index)]
        direction = "below"
        bands = (index,)
    else:
        raise WaterThresholdError(f"Unknown water index '{index}'")

    with rasterio.open(raster_path) as source:
        height, width = source.height, source.width
        data = source.read(indexes=[position + 1 for position in positions]).astype("float32")
        transform: Affine = source.transform
        crs = source.crs

    nodata = None
    if nodata_values:
        first = nodata_values[0]
        if first is not None and all(value == first for value in nodata_values if value is not None):
            nodata = float(first)

    finite = np.isfinite(data).all(axis=0)
    if nodata is not None:
        # Strict all-band validity, matching the classification contracts: any
        # band at nodata invalidates the pixel for this product.
        finite &= ~(data == nodata).any(axis=0)
    valid = finite.copy()
    if study_area is not None:
        valid &= study_area

    if index in SPECTRAL_WATER_INDICES:
        a, b = data[0], data[1]
        denominator = a + b
        valid &= np.isfinite(denominator) & (denominator != 0)
        index_values = np.zeros_like(a)
        np.divide(a - b, denominator, out=index_values, where=valid)
        threshold = otsu_threshold(index_values[valid])
        water = valid & (index_values > threshold)
    else:
        backscatter = data[0]
        valid &= np.isfinite(backscatter)
        if not valid.any():
            raise WaterThresholdError("No valid pixels available for the water threshold")
        threshold = otsu_threshold(backscatter[valid])
        water = valid & (backscatter < threshold)

    values = np.full((height, width), -1, dtype=np.int8)
    values[valid] = 0
    values[water] = 1
    counts = {
        "valid": int(valid.sum()),
        "water": int(water.sum()),
        "non_water": int((valid & ~water).sum()),
        "total": int(height * width),
    }
    pixel_area = abs(transform.a * transform.e - transform.b * transform.d)
    areas = {
        "pixel_sqm": pixel_area,
        "valid_sqm": counts["valid"] * pixel_area,
        "water_sqm": counts["water"] * pixel_area,
    }
    grid = {
        "crs": str(crs) if crs else None,
        "transform": [float(v) for v in transform[:6]],
        "width": width,
        "height": height,
    }
    return WaterThresholdResult(
        index=index,
        bands=bands,
        direction=direction,
        threshold=round(threshold, 6),
        method="otsu",
        values=values,
        valid=valid,
        counts=counts,
        areas=areas,
        grid=grid,
    )


def values_to_json(values: np.ndarray) -> list[list[int | None]]:
    """int8 grid (-1 invalid) → JSON-friendly nested arrays."""
    height, width = values.shape
    flat = values.reshape(-1)
    return [
        [int(v) if v >= 0 else None for v in flat[row * width : (row + 1) * width]]
        for row in range(height)
    ]


def valid_to_json(valid: np.ndarray) -> list[list[bool]]:
    return [[bool(v) for v in row] for row in valid]
