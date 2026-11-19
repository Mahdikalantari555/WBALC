"""Register explicitly mapped single-band GeoTIFFs without implicit resampling."""
import json
import shutil
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

import anyio
import numpy as np
import rasterio
from fastapi import APIRouter, Form, HTTPException, UploadFile

from .datasets import upload_geotiff
from .deps import SessionDep, SettingsDep, get_project
from .scenes import register_scene

router = APIRouter(prefix='/projects/{project_id}', tags=['raster-intake'])


def stack(paths, names, target, limit):
    with ExitStack() as resources:
        sources = [resources.enter_context(rasterio.open(p, driver="GTiff")) for p in paths]
        first = sources[0]
        if first.width * first.height * len(sources) > limit:
            raise ValueError('Stack exceeds the raster element limit.')
        if any(s.count != 1 for s in sources):
            raise ValueError('Every stack input must contain exactly one band.')
        if any((s.shape, s.crs, s.transform) != (first.shape, first.crs, first.transform) for s in sources):
            raise ValueError('All bands must have identical dimensions, CRS and transform. Align them before importing.')
        if any(s.scales != (1.0,) or s.offsets != (0.0,) for s in sources):
            raise ValueError('Apply band scale and offset before stacking; they cannot be discarded.')
        with rasterio.open(target, 'w', driver='GTiff', height=first.height, width=first.width,
                           count=len(sources), dtype='float64', transform=first.transform,
                           crs=first.crs, nodata=np.nan, tiled=True, compress='deflate', BIGTIFF='IF_SAFER') as dest:
            for i, (source, name) in enumerate(zip(sources, names), 1):
                dest.set_band_description(i, name)
                for _, window in dest.block_windows(i):
                    data = source.read(1, window=window, masked=True, out_dtype='float64').filled(np.nan)
                    dest.write(np.where(np.isfinite(data), data, np.nan), i, window=window)


@router.post('/raster-stack', status_code=201)
async def upload_stack(
    project_id: int, session: SessionDep, settings: SettingsDep, files: list[UploadFile],
    band_names: Annotated[str, Form()], sensor: Annotated[Literal['Sentinel-1', 'Sentinel-2'], Form()],
    kind: Annotated[Literal['dataset', 'scene'], Form()] = 'dataset',
    acquisition_datetime: Annotated[str | None, Form()] = None,
    platform: Annotated[str | None, Form(max_length=100)] = None,
):
    await get_project(session, project_id)
    try:
        names = json.loads(band_names)
    except ValueError:
        names = None
    if (not isinstance(names, list) or len(names) != len(files) or not 1 <= len(files) <= 32
            or any(not isinstance(n, str) or not n.strip() or ',' in n or len(n) > 64 for n in names)
            or len({n.strip().casefold() for n in names}) != len(names)):
        raise HTTPException(422, 'Supply one unique name per input band (1–32 files).')
    names = [n.strip().casefold() for n in names]
    if any(Path(f.filename or '').suffix.lower() not in {'.tif', '.tiff'} for f in files):
        raise HTTPException(422, 'Stack inputs must be GeoTIFF files.')
    if sum(f.size or 0 for f in files) > settings.max_upload_bytes:
        raise HTTPException(413, 'Combined source files exceed the upload limit.')
    with TemporaryDirectory(prefix='wbalc-stack-') as tmp:
        paths = [Path(tmp) / f'{i}.tif' for i in range(len(files))]
        for upload, path in zip(files, paths):
            def copy():
                with path.open('wb') as out:
                    shutil.copyfileobj(upload.file, out)
            await anyio.to_thread.run_sync(copy)
            await upload.close()
        target = Path(tmp) / 'stack.tif'
        try:
            await anyio.to_thread.run_sync(stack, paths, names, target, settings.max_raster_elements)
        except (ValueError, rasterio.errors.RasterioError) as exc:
            raise HTTPException(422, str(exc)) from exc
        stamp = (acquisition_datetime or 'bands')[:10]
        stamp = stamp if stamp.replace('-', '').isdigit() else 'bands'
        with target.open('rb') as source:
            file = UploadFile(source, filename=f'{sensor}-{stamp}.tif')
            if kind == 'scene':
                return await register_scene(
                    project_id, file, session, settings, sensor=sensor, acquisition_datetime=acquisition_datetime,
                    platform=platform, band_names=','.join(names), product_type=None, product_level=None,
                    polarization=','.join(names) if sensor == 'Sentinel-1' and set(names) <= {'vv', 'vh', 'hh', 'hv'} else None,
                    acquisition_mode=None, orbit_direction=None, relative_orbit=None, processing_baseline=None,
                    native_band_resolutions=None, acquisition_metadata=None, product_metadata=None,
                )
            return await upload_geotiff(project_id, file, session, settings, ','.join(names), sensor)
