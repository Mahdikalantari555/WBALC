"""Import explicitly mapped single-band GeoTIFFs as one common-grid raster."""
from __future__ import annotations

import json
import math
import re
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

import anyio
import numpy as np
import rasterio
from affine import Affine
from fastapi import APIRouter, Form, HTTPException, UploadFile
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from ..services.schema_service import is_scl_band
from .datasets import upload_geotiff
from .deps import SessionDep, SettingsDep, get_project
from .scenes import register_scene

router = APIRouter(prefix='/projects/{project_id}', tags=['raster-intake'])
CHUNK_BYTES = 1024 * 1024


class UploadLimitExceeded(Exception):
    """The combined stack inputs exceed the configured upload budget."""


@dataclass(frozen=True)
class _TargetGrid:
    width: int
    height: int
    crs: object
    transform: Affine

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width


def _pixel_resolution(source) -> tuple[float, float]:
    transform = source.transform
    return math.hypot(float(transform.a), float(transform.d)), math.hypot(float(transform.b), float(transform.e))


def _axis_resolution(source) -> tuple[float, float]:
    transform = source.transform
    if not math.isclose(transform.b, 0.0, abs_tol=1e-12) or not math.isclose(transform.d, 0.0, abs_tol=1e-12):
        raise ValueError('Rotated or sheared band grids cannot be auto-aligned; prepare these bands on a common north-up grid.')
    if transform.a <= 0 or transform.e >= 0:
        raise ValueError('Only north-up band grids can be auto-aligned during stacking.')
    return float(transform.a), -float(transform.e)


def _same_grid(source, reference) -> bool:
    return (
        source.width == reference.width
        and source.height == reference.height
        and source.crs == reference.crs
        and source.transform == reference.transform
    )


def _target_grid(sources):
    first = sources[0]
    if all(_same_grid(source, first) for source in sources):
        return first, False

    if first.crs is None or any(source.crs != first.crs for source in sources):
        raise ValueError('Bands with different grids must share the same declared CRS; reprojection is not performed during band stacking.')

    resolutions = [_axis_resolution(source) for source in sources]
    # Use the finest native grid where every source resolution is an integer
    # multiple. Different native extents are allowed; output is cropped to the
    # common pixel-aligned overlap rather than inventing coverage.
    candidates = [
        index for index, (rx, ry) in enumerate(resolutions)
        if all(rx <= ox * (1 + 1e-9) and ry <= oy * (1 + 1e-9) for ox, oy in resolutions)
    ]
    if not candidates:
        raise ValueError('Bands are not a nested resolution pyramid. Select a single target grid or align them before importing.')
    target_index = min(candidates, key=lambda index: resolutions[index][0] * resolutions[index][1])
    target = sources[target_index]
    target_x, target_y = resolutions[target_index]
    if target_x <= 0 or target_y <= 0:
        raise ValueError('Band resolution must be positive.')

    for source, (source_x, source_y) in zip(sources, resolutions):
        ratios = (source_x / target_x, source_y / target_y)
        if any(
            ratio < 1 - 1e-9
            or not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-8)
            for ratio in ratios
        ):
            raise ValueError('Band resolutions must be integer multiples on the same aligned grid (for example, 10 m and 20 m).')
        # A coarser grid must align on its own pixel lattice, not merely land on
        # any fine-grid pixel. Otherwise its centres are half a source pixel off.
        col_offset = (float(source.transform.c) - float(target.transform.c)) / source_x
        row_offset = (float(target.transform.f) - float(source.transform.f)) / source_y
        if not math.isclose(col_offset, round(col_offset), rel_tol=0, abs_tol=1e-8) or not math.isclose(row_offset, round(row_offset), rel_tol=0, abs_tol=1e-8):
            raise ValueError('Band grids are shifted by a fractional source pixel; sub-pixel alignment is not inferred.')

    bounds = [tuple(float(value) for value in source.bounds) for source in sources]
    left = max(entry[0] for entry in bounds)
    bottom = max(entry[1] for entry in bounds)
    right = min(entry[2] for entry in bounds)
    top = min(entry[3] for entry in bounds)
    if left >= right or bottom >= top:
        raise ValueError('Band footprints do not overlap in the shared CRS.')

    # Keep only target pixels fully contained in the common footprint. The
    # small pixel-space tolerance absorbs floating-point representation noise,
    # not real half-pixel shifts.
    epsilon = 1e-8
    col_start = max(0, math.ceil((left - float(target.transform.c)) / target_x - epsilon))
    col_stop = min(target.width, math.floor((right - float(target.transform.c)) / target_x + epsilon))
    row_start = max(0, math.ceil((float(target.transform.f) - top) / target_y - epsilon))
    row_stop = min(target.height, math.floor((float(target.transform.f) - bottom) / target_y + epsilon))
    if col_stop <= col_start or row_stop <= row_start:
        raise ValueError('Band footprints have no full target pixels in common after alignment.')

    return _TargetGrid(
        width=col_stop - col_start,
        height=row_stop - row_start,
        crs=target.crs,
        transform=target.transform * Affine.translation(col_start, row_start),
    ), True


_CONTINUOUS_BANDS = {
    'blue', 'green', 'red', 'coastal', 'rededge1', 'rededge2', 'rededge3',
    'nir', 'nir08', 'nir_narrow', 'water_vapor', 'cirrus', 'swir1', 'swir16', 'swir2', 'swir22',
    'b01', 'b02', 'b03', 'b04', 'b05', 'b06', 'b07', 'b08', 'b8', 'b8a', 'b09', 'b10', 'b11', 'b12',
    'vv', 'vh', 'hh', 'hv',
}
_CATEGORICAL_BANDS = {'scl', 'scene_classification', 'sceneclassification', 'classification', 'qa', 'mask', 'cloud_mask'}
_RESAMPLING = {
    'nearest': Resampling.nearest,
    'bilinear': Resampling.bilinear,
    'cubic': Resampling.cubic,
}


def _resampling_for(name: str, requested: str) -> Resampling:
    normalized = name.strip().casefold()
    # Preserve class labels and QA bits even if a caller asks to smooth all
    # continuous bands explicitly.
    if normalized in _CATEGORICAL_BANDS or is_scl_band(normalized):
        return Resampling.nearest
    if requested != 'auto':
        return _RESAMPLING[requested]
    if normalized in _CONTINUOUS_BANDS:
        return Resampling.bilinear
    # Unknown bands use nearest-neighbour as the least transformative choice.
    return Resampling.nearest


def _band_data(source, window, scale: float, offset: float) -> np.ndarray:
    masked = source.read(1, window=window, masked=True, out_dtype='float64')
    data = masked.filled(np.nan)
    valid = np.isfinite(data)
    if scale != 1.0 or offset != 0.0:
        data[valid] = data[valid] * scale + offset
    data[~valid] = np.nan
    return data


def stack(paths, names, target_path, limit, resampling='auto'):
    """Write named bands on the finest co-registered common-overlap grid.

    Different native resolutions are accepted only when they share a CRS and
    have a pixel-aligned overlapping footprint with integer-nested resolutions.
    Continuous Sentinel bands use bilinear interpolation; SCL/QA masks use
    nearest-neighbour. Source scale/offset are applied to samples so the output
    uses physical values and identity scale.
    """
    if not paths or len(paths) != len(names):
        raise ValueError('Supply at least one source raster and one name per band.')
    with ExitStack() as resources:
        sources = [resources.enter_context(rasterio.open(path, driver='GTiff')) for path in paths]
        first = sources[0]
        if any(source.count != 1 for source in sources):
            raise ValueError('Every stack input must contain exactly one band. Exclude merged/multiband products and select the individual band files.')
        target, _ = _target_grid(sources)
        if target.width * target.height * len(sources) > limit:
            raise ValueError('Stack exceeds the raster element limit at its highest-resolution input grid.')

        target_resolution = list(_pixel_resolution(target))
        band_records = []
        for source, name in zip(sources, names):
            needs_resampling = not _same_grid(source, target)
            source_resolution = _axis_resolution(source) if needs_resampling else _pixel_resolution(source)
            method = _resampling_for(name, resampling).name if needs_resampling else 'none'
            scale = float(source.scales[0])
            offset = float(source.offsets[0])
            if not math.isfinite(scale) or not math.isfinite(offset):
                raise ValueError(f'Band {name!r} has a non-finite scale or offset.')
            band_records.append({
                'name': name,
                'source_width': source.width,
                'source_height': source.height,
                'source_resolution': [source_resolution[0], source_resolution[1]],
                'target_resolution': target_resolution,
                'resampled': needs_resampling,
                'resampling': method,
                'source_scale': scale,
                'source_offset': offset,
            })

        with rasterio.open(
            target_path, 'w', driver='GTiff', height=target.height, width=target.width,
            count=len(sources), dtype='float64', transform=target.transform,
            crs=target.crs, nodata=np.nan, tiled=True, compress='deflate', BIGTIFF='IF_SAFER',
        ) as dest:
            for index, (source, name, record) in enumerate(zip(sources, names, band_records), 1):
                scale = record['source_scale']
                offset = record['source_offset']
                dest.set_band_description(index, name)
                dest.update_tags(index, **{
                    'WBALC_SOURCE_RESOLUTION': json.dumps(record['source_resolution']),
                    'WBALC_RESAMPLED': str(record['resampled']).lower(),
                    'WBALC_RESAMPLING': record['resampling'],
                    'WBALC_SOURCE_SCALE': str(scale),
                    'WBALC_SOURCE_OFFSET': str(offset),
                })
                if _same_grid(source, target):
                    for _, window in dest.block_windows(index):
                        dest.write(_band_data(source, window, scale, offset), index, window=window)
                    continue
                with WarpedVRT(
                    source,
                    crs=target.crs,
                    transform=target.transform,
                    width=target.width,
                    height=target.height,
                    nodata=np.nan,
                    dtype='float64',
                    resampling=_resampling_for(name, resampling),
                ) as aligned:
                    for _, window in dest.block_windows(index):
                        dest.write(_band_data(aligned, window, scale, offset), index, window=window)

        return {
            'policy': 'common-native-grid-v1',
            'resampling_request': resampling,
            'target_grid': {
                'crs': target.crs.to_string() if target.crs else None,
                'transform': [float(value) for value in target.transform[:6]],
                'width': target.width,
                'height': target.height,
                'resolution': target_resolution,
            },
            'bands': band_records,
            'resampling_performed': any(record['resampled'] for record in band_records),
            'reprojection_performed': False,
        }


def _merged_product(filename: str) -> bool:
    stem = Path(filename).stem.casefold()
    return re.search(r'(?:^|[_-])merged(?:$|[_-])', stem) is not None


@router.post('/raster-stack', status_code=201)
async def upload_stack(
    project_id: int, session: SessionDep, settings: SettingsDep, files: list[UploadFile],
    band_names: Annotated[str, Form()], sensor: Annotated[Literal['Sentinel-1', 'Sentinel-2'], Form()],
    kind: Annotated[Literal['dataset', 'scene'], Form()] = 'dataset',
    acquisition_datetime: Annotated[str | None, Form()] = None,
    platform: Annotated[str | None, Form(max_length=100)] = None,
    product_type: Annotated[str | None, Form(max_length=100)] = None,
    product_level: Annotated[str | None, Form(max_length=50)] = None,
    polarization: Annotated[str | None, Form()] = None,
    acquisition_mode: Annotated[str | None, Form(max_length=30)] = None,
    orbit_direction: Annotated[Literal['ascending', 'descending'] | None, Form()] = None,
    relative_orbit: Annotated[int | None, Form(ge=1, le=999)] = None,
    processing_baseline: Annotated[str | None, Form(max_length=50)] = None,
    native_band_resolutions: Annotated[str | None, Form()] = None,
    acquisition_metadata: Annotated[str | None, Form()] = None,
    product_metadata: Annotated[str | None, Form()] = None,
    resampling: Annotated[Literal['auto', 'nearest', 'bilinear', 'cubic'], Form()] = 'auto',
):
    await get_project(session, project_id)
    try:
        names = json.loads(band_names)
    except ValueError:
        names = None
    if (not isinstance(names, list) or len(names) != len(files) or not 1 <= len(files) <= 32
            or any(not isinstance(name, str) or not name.strip() or ',' in name or len(name) > 64 for name in names)
            or len({name.strip().casefold() for name in names}) != len(names)):
        raise HTTPException(422, 'Supply one unique name per input band (1–32 files).')
    names = [name.strip().casefold() for name in names]
    if any(Path(file.filename or '').suffix.lower() not in {'.tif', '.tiff'} for file in files):
        raise HTTPException(422, 'Stack inputs must be GeoTIFF files.')
    merged = [file.filename or 'merged.tif' for file in files if _merged_product(file.filename or '')]
    if merged:
        raise HTTPException(422, 'Merged/multiband products are excluded from band stacks; select the individual named single-band GeoTIFFs.')
    if sum(file.size or 0 for file in files) > settings.max_upload_bytes:
        raise HTTPException(413, 'Combined source files exceed the upload limit.')

    with TemporaryDirectory(prefix='wbalc-stack-') as tmp:
        paths = [Path(tmp) / f'{index}.tif' for index in range(len(files))]
        copied = 0

        def copy_upload(upload: UploadFile, path: Path, remaining: int) -> int:
            size = 0
            with path.open('wb') as output:
                while chunk := upload.file.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > remaining:
                        raise UploadLimitExceeded
                    output.write(chunk)
            return size

        try:
            for upload, path in zip(files, paths):
                copied += await anyio.to_thread.run_sync(copy_upload, upload, path, settings.max_upload_bytes - copied)
        except UploadLimitExceeded as exc:
            raise HTTPException(413, 'Combined source files exceed the upload limit.') from exc
        finally:
            for upload in files:
                await upload.close()

        target = Path(tmp) / 'stack.tif'
        try:
            alignment = await anyio.to_thread.run_sync(stack, paths, names, target, settings.max_raster_elements, resampling)
        except (ValueError, rasterio.errors.RasterioError) as exc:
            raise HTTPException(422, str(exc)) from exc

        stamp = (acquisition_datetime or 'bands')[:10]
        stamp = stamp if stamp.replace('-', '').isdigit() else 'bands'
        with target.open('rb') as source:
            file = UploadFile(source, filename=f'{sensor}-{stamp}.tif')
            if kind == 'scene':
                try:
                    acquisition_data = json.loads(acquisition_metadata) if acquisition_metadata else {}
                except ValueError as exc:
                    raise HTTPException(422, 'acquisition_metadata must be valid JSON') from exc
                if not isinstance(acquisition_data, dict):
                    raise HTTPException(422, 'acquisition_metadata must be a JSON object')
                acquisition_data['wbalc_stack'] = alignment
                return await register_scene(
                    project_id, file, session, settings, sensor=sensor, acquisition_datetime=acquisition_datetime,
                    platform=platform, band_names=','.join(names), product_type=product_type, product_level=product_level,
                    polarization=polarization,
                    acquisition_mode=acquisition_mode, orbit_direction=orbit_direction, relative_orbit=relative_orbit,
                    processing_baseline=processing_baseline,
                    native_band_resolutions=native_band_resolutions, acquisition_metadata=json.dumps(acquisition_data),
                    product_metadata=product_metadata,
                )
            return await upload_geotiff(project_id, file, session, settings, ','.join(names), sensor)
