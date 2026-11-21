"""Dataset ingestion endpoints (dataset-ingestion capability)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import anyio
from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete as sa_delete, select, update as sa_update

from ..config import Settings
from ..models import Dataset, Export, Label, Scene
from ..schemas import DatasetOut
from ..services.raster_service import (
    RasterError,
    extract_band_identity,
    extract_metadata,
    make_grid,
)
from ..services.raster_preview import PreviewError, inspect_raster_pixel, render_raster_preview
from ..services.schema_service import build_band_schema
from ..storage import project_dir, unique_name
from .deps import SessionDep, SettingsDep, get_dataset, get_project

router = APIRouter(prefix="/projects/{project_id}", tags=["datasets"])

ALLOWED_SUFFIXES = {".tif", ".tiff"}
CHUNK = 1024 * 1024


def dataset_out(dataset: Dataset, settings: Settings) -> DatasetOut:
    """DatasetOut enriched with computed size and patch-grid metadata."""
    out = DatasetOut.model_validate(dataset)
    path = Path(dataset.path)
    # `size_bytes` is the recorded size of the bytes at registration; it is not
    # recomputed as "whatever is on disk now".
    if dataset.size_bytes is None:
        out.size_bytes = path.stat().st_size if path.exists() else 0
    grid = make_grid(dataset.height, dataset.width, settings.patch_size, settings.resolved_stride())
    rows, cols = grid.shape
    out.patch_grid = {
        "patch_size": settings.patch_size,
        "stride": settings.resolved_stride(),
        "rows": rows,
        "cols": cols,
        "total_patches": rows * cols,
    }
    return out


@router.post("/upload", response_model=DatasetOut, status_code=201)
async def upload_geotiff(
    project_id: int,
    file: UploadFile,
    session: SessionDep,
    settings: SettingsDep,
    band_names: str | None = Form(default=None),
    sensor: str | None = Form(default=None),
) -> Dataset:
    """Store one GeoTIFF and record the band identity it declares.

    `band_names` (comma-separated) and `sensor` are optional *explicit* caller
    declarations for files whose bands are unnamed; without them the dataset is
    stored as "schema undeclared" and inference against it requires an override.
    """
    await get_project(session, project_id)

    filename = file.filename or "upload.tif"
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Only GeoTIFF files (.tif/.tiff) are accepted")

    dest_dir = project_dir(settings, "uploads", project_id)
    dest = dest_dir / unique_name(filename)

    size = 0
    # The hash is computed from the same bytes that are written, so it describes
    # the stored file rather than a second read of it.
    digest = hashlib.sha256()
    try:
        async with await anyio.open_file(dest, "wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds size limit")
                digest.update(chunk)
                await out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Empty file")

    try:
        meta = await anyio.to_thread.run_sync(extract_metadata, dest)
    except RasterError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    declared_names = None
    source = "raster-metadata"
    if band_names and band_names.strip():
        declared_names = [part.strip() for part in band_names.split(",")]
        if len(declared_names) != meta["bands"]:
            dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"band_names declares {len(declared_names)} names but the raster has "
                    f"{meta['bands']} bands"
                ),
            )
        source = "request"
    else:
        try:
            identity = await anyio.to_thread.run_sync(extract_band_identity, dest)
        except RasterError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        declared_names = identity["band_names"]

    dataset = Dataset(
        project_id=project_id,
        filename=filename,
        path=str(dest),
        content_sha256=digest.hexdigest(),
        size_bytes=size,
        band_schema=build_band_schema(
            band_count=meta["bands"],
            band_names=declared_names,
            sensor=(sensor.strip() if sensor and sensor.strip() else None),
            source=source,
        ),
        **meta,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset_out(dataset, settings)


@router.get("/dataset", response_model=list[DatasetOut])
async def list_datasets(project_id: int, session: SessionDep, settings: SettingsDep):
    await get_project(session, project_id)
    result = await session.execute(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.id)
    )
    return [dataset_out(d, settings) for d in result.scalars()]


@router.get("/dataset/{dataset_id}", response_model=DatasetOut)
async def read_dataset(project_id: int, dataset_id: int, session: SessionDep, settings: SettingsDep):
    await get_project(session, project_id)
    return dataset_out(await get_dataset(session, project_id, dataset_id), settings)


@router.get("/dataset/{dataset_id}/file")
async def download_dataset_file(project_id: int, dataset_id: int, session: SessionDep):
    """Serve the original uploaded GeoTIFF bytes (for client-side band rendering)."""
    await get_project(session, project_id)
    dataset = await get_dataset(session, project_id, dataset_id)
    path = Path(dataset.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file missing from storage")
    return FileResponse(path, media_type="image/tiff", filename=dataset.filename)


@router.get("/dataset/{dataset_id}/preview")
async def preview_dataset_file(
    project_id: int,
    dataset_id: int,
    session: SessionDep,
    mode: str = "true-color",
    size: int = Query(default=1400, ge=16, le=2048),
    x0: int | None = Query(default=None, ge=0),
    y0: int | None = Query(default=None, ge=0),
    x1: int | None = Query(default=None, ge=1),
    y1: int | None = Query(default=None, ge=1),
    upscale: bool = False,
) -> Response:
    """GDAL preview fallback for TIFF variants not decoded by geotiff.js."""
    await get_project(session, project_id)
    dataset = await get_dataset(session, project_id, dataset_id)
    path = Path(dataset.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Dataset file missing from storage")
    coordinates = (x0, y0, x1, y1)
    if any(value is not None for value in coordinates) and not all(value is not None for value in coordinates):
        raise HTTPException(status_code=422, detail="A preview window must provide x0, y0, x1, and y1")
    window = tuple(coordinates) if all(value is not None for value in coordinates) else None
    names = (dataset.band_schema or {}).get("band_names")
    try:
        png = await anyio.to_thread.run_sync(
            lambda: render_raster_preview(path, mode=mode, size=size, names=names, window=window, upscale=upscale)
        )
    except PreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=60"})


@router.get("/dataset/{dataset_id}/pixel")
async def inspect_dataset_pixel(
    project_id: int,
    dataset_id: int,
    session: SessionDep,
    x: int = Query(ge=0),
    y: int = Query(ge=0),
    mode: str = "true-color",
) -> dict:
    """GDAL pixel-probe fallback for TIFFs the browser decoder cannot inspect."""
    await get_project(session, project_id)
    dataset = await get_dataset(session, project_id, dataset_id)
    path = Path(dataset.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Dataset file missing from storage")
    names = (dataset.band_schema or {}).get("band_names")
    try:
        return await anyio.to_thread.run_sync(
            lambda: inspect_raster_pixel(path, x=x, y=y, mode=mode, names=names)
        )
    except PreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/dataset/{dataset_id}", status_code=204)
async def delete_dataset(project_id: int, dataset_id: int, session: SessionDep) -> None:
    """Delete a dataset with its stored file, labels and exports."""
    await get_project(session, project_id)
    dataset = await get_dataset(session, project_id, dataset_id)

    exports = (
        await session.execute(select(Export).where(Export.dataset_id == dataset_id))
    ).scalars().all()
    for export in exports:
        Path(export.path).unlink(missing_ok=True)
    await session.execute(sa_delete(Export).where(Export.dataset_id == dataset_id))
    await session.execute(sa_delete(Label).where(Label.dataset_id == dataset_id))
    # Keep the scene link honest before the row disappears (SET NULL also covers
    # this, but SQLite needs the pragma for that path — do it explicitly).
    await session.execute(
        sa_update(Scene).where(Scene.dataset_id == dataset_id).values(dataset_id=None)
    )
    source_path = Path(dataset.path)
    await session.delete(dataset)
    await session.commit()

    # Scene-backed active-learning datasets share their immutable source file.
    # Remove bytes only after the last Scene/Dataset reference is gone.
    dataset_reference = await session.execute(
        select(Dataset.id).where(Dataset.path == str(source_path)).limit(1)
    )
    scene_reference = await session.execute(
        select(Scene.id).where(Scene.storage_path == str(source_path)).limit(1)
    )
    if dataset_reference.scalar_one_or_none() is None and scene_reference.scalar_one_or_none() is None:
        source_path.unlink(missing_ok=True)
