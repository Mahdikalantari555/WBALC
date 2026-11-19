"""Bounded GDAL-backed PNG previews and exact pixel probes for GeoTIFFs."""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Sequence

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.windows import Window


class PreviewError(ValueError):
    """The requested raster preview is invalid or unreadable."""


ALIASES = {
    'red': {'red', 'b04', 'b4'},
    'green': {'green', 'b03', 'b3'},
    'blue': {'blue', 'b02', 'b2'},
    'nir': {'nir', 'nir08', 'nir_08', 'b08', 'b8'},
}


def _channels(mode: str, count: int, names: Sequence[str | None] | None):
    normalized = [value.strip().casefold() if value else '' for value in (names or [])]

    def lookup(name: str) -> int:
        aliases = ALIASES[name]
        return next((index for index, value in enumerate(normalized) if value in aliases), -1)

    fallback = {'channels': [0, 0, 0], 'difference': None}
    if mode.startswith('band:'):
        try:
            index = int(mode.split(':', 1)[1])
        except ValueError as exc:
            raise PreviewError('Band index must be an integer.') from exc
        if not 0 <= index < count:
            raise PreviewError(f'Band index {index} is outside the raster band count {count}.')
        return {'channels': [index, index, index], 'difference': None}
    if mode.startswith('nd:'):
        try:
            _, first, second = mode.split(':')
            a, b = int(first), int(second)
        except (ValueError, TypeError) as exc:
            raise PreviewError('Band difference mode must be nd:first:second.') from exc
        if not (0 <= a < count and 0 <= b < count) or a == b:
            raise PreviewError('Band difference indices must refer to two different raster bands.')
        return {'channels': [a, b], 'difference': (a, b)}
    if mode == 'true-color':
        red, green, blue = lookup('red'), lookup('green'), lookup('blue')
        return {'channels': [red, green, blue] if min(red, green, blue) >= 0 else fallback['channels'], 'difference': None}
    if mode == 'false-color':
        nir, red, green = lookup('nir'), lookup('red'), lookup('green')
        return {'channels': [nir, red, green] if min(nir, red, green) >= 0 else fallback['channels'], 'difference': None}
    if mode == 'ndvi':
        nir, red = lookup('nir'), lookup('red')
        return {'channels': [nir, red] if min(nir, red) >= 0 else fallback['channels'],
                'difference': (nir, red) if min(nir, red) >= 0 else None}
    raise PreviewError(f"Unsupported preview mode '{mode}'.")


def _stretch(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    finite = valid & np.isfinite(values)
    samples = values[finite]
    if not samples.size:
        return np.zeros(values.shape, dtype=np.uint8)
    step = max(1, math.ceil(samples.size / 200_000))
    sample = samples[::step]
    low, high = np.percentile(sample, [2, 98])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        high = low + 1.0
    scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
    scaled[~finite] = 0.0
    return np.round(scaled * 255).astype(np.uint8)


def _band_names(source, names: Sequence[str | None] | None) -> list[str | None]:
    if names is not None:
        return list(names)
    return [
        description or source.tags(index + 1).get('NAME') or source.tags(index + 1).get('BAND_NAME')
        for index, description in enumerate(source.descriptions)
    ]


def render_raster_preview(
    path: str | Path,
    *,
    mode: str = 'true-color',
    size: int = 1400,
    names: Sequence[str | None] | None = None,
    window: tuple[int, int, int, int] | None = None,
    upscale: bool = False,
) -> bytes:
    """Render a bounded, mask-aware PNG, optionally for one pixel window.

    Full-image reads are downsampled by GDAL before materialising the arrays.
    Window reads stay exact unless `upscale` is requested for blocky review
    thumbnails. Source files and their affine grids are never modified.
    """
    if not 16 <= size <= 2048:
        raise PreviewError('Preview size must be between 16 and 2048 pixels.')
    try:
        with rasterio.open(path) as source:
            if source.count < 1 or source.width < 1 or source.height < 1:
                raise PreviewError('The raster has no image data.')
            band_names = _band_names(source, names)
            view = _channels(mode, source.count, band_names)
            channels = view['channels']
            unique = list(dict.fromkeys(channels))

            read_window = None
            if window is not None:
                x0, y0, x1, y1 = window
                if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0 or x1 > source.width or y1 > source.height:
                    raise PreviewError('Preview window is outside the raster bounds.')
                base_width, base_height = x1 - x0, y1 - y0
                read_window = Window(x0, y0, base_width, base_height)
                ratio = size / max(base_width, base_height) if upscale else min(1.0, size / max(base_width, base_height))
                resampling = Resampling.nearest if upscale else Resampling.bilinear
            else:
                base_width, base_height = source.width, source.height
                ratio = min(1.0, size / max(base_width, base_height))
                resampling = Resampling.bilinear
            out_width = max(1, round(base_width * ratio))
            out_height = max(1, round(base_height * ratio))
            kwargs = {
                'indexes': [index + 1 for index in unique],
                'out_shape': (len(unique), out_height, out_width),
                'masked': True,
                'resampling': resampling,
            }
            if read_window is not None:
                kwargs['window'] = read_window
            masked = source.read(**kwargs)
            data = np.asarray(masked.astype('float32').filled(np.nan), dtype=np.float32)
            masks = np.ma.getmaskarray(masked)
            valid_by_band = (~masks) & np.isfinite(data)
            valid = valid_by_band.all(axis=0)
            rgb = np.zeros((out_height, out_width, 3), dtype=np.uint8)
            alpha = np.where(valid, 255, 0).astype(np.uint8)
            unique_index = {band: index for index, band in enumerate(unique)}
            difference = view['difference']
            if difference is not None:
                first, second = difference
                a = data[unique_index[first]]
                b = data[unique_index[second]]
                denominator = a + b
                valid &= np.isfinite(denominator) & (denominator != 0)
                index = np.zeros_like(a, dtype=np.float32)
                np.divide(a - b, denominator, out=index, where=valid)
                value = np.clip((index + 1.0) / 2.0, 0.0, 1.0)
                rgb[..., 0] = np.round(225 * (1 - value) + 25 * value).astype(np.uint8)
                rgb[..., 1] = np.round(115 * (1 - value) + 175 * value).astype(np.uint8)
                rgb[..., 2] = np.round(80 * (1 - value) + 72 * value).astype(np.uint8)
                alpha = np.where(valid, 255, 0).astype(np.uint8)
            else:
                for channel, band in enumerate(channels):
                    source_index = unique_index[band]
                    rgb[..., channel] = _stretch(data[source_index], valid_by_band[source_index])
            rgba = np.dstack((rgb, alpha))
            output = io.BytesIO()
            Image.fromarray(rgba).save(output, format='PNG', optimize=True)
            return output.getvalue()
    except PreviewError:
        raise
    except Exception as exc:
        raise PreviewError(f'GDAL could not render this GeoTIFF: {exc}') from exc


def inspect_raster_pixel(
    path: str | Path,
    *,
    x: int,
    y: int,
    mode: str = 'true-color',
    names: Sequence[str | None] | None = None,
) -> dict:
    """Read exact band values for one pixel, honoring nodata and dataset masks."""
    try:
        with rasterio.open(path) as source:
            if not 0 <= x < source.width or not 0 <= y < source.height:
                raise PreviewError('Pixel coordinate is outside the raster bounds.')
            band_names = _band_names(source, names)
            view = _channels(mode, source.count, band_names)
            channels = view['channels']
            unique = list(dict.fromkeys(channels))
            masked = source.read(
                indexes=[index + 1 for index in unique],
                window=Window(x, y, 1, 1),
                masked=True,
            )
            values = np.asarray(masked.astype('float64').filled(np.nan), dtype=np.float64)[:, 0, 0]
            masks = np.ma.getmaskarray(masked)[:, 0, 0]
            by_band: dict[int, float | None] = {
                band: float(values[index]) if not masks[index] and np.isfinite(values[index]) else None
                for index, band in enumerate(unique)
            }
            result = {
                'bands': [
                    {'name': band_names[band] if band < len(band_names) and band_names[band] else f'#{band + 1}',
                     'value': by_band[band]}
                    for band in unique
                ],
                'difference': view['difference'] is not None,
                'index': None,
            }
            if view['difference'] is not None:
                first, second = view['difference']
                a, b = by_band[first], by_band[second]
                if a is not None and b is not None and a + b != 0:
                    result['index'] = (a - b) / (a + b)
            return result
    except PreviewError:
        raise
    except Exception as exc:
        raise PreviewError(f'GDAL could not inspect this GeoTIFF pixel: {exc}') from exc
