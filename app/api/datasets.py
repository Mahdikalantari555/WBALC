"""Dataset ingestion endpoints (dataset-ingestion capability)."""

from __future__ import annotations

from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete as sa_delete, select

from ..config import Settings
from ..models import Dataset, Export, Label
from ..schemas import DatasetOut
from ..services.raster_service import RasterError, extract_metadata, make_grid
from ..storage import project_dir, unique_name
from .deps import SessionDep, SettingsDep, get_dataset, get_project

router = APIRouter(prefix="/projects/{project_id}", tags=["datasets"])

ALLOWED_SUFFIXES = {".tif", ".tiff"}
CHUNK = 1024 * 1024


def dataset_out(dataset: Dataset, settings: Settings) -> DatasetOut:
    """DatasetOut enriched with computed size and patch-grid metadata."""
    out = DatasetOut.model_validate(dataset)
    path = Path(dataset.path)
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
    project_id: int, file: UploadFile, session: SessionDep, settings: SettingsDep
) -> Dataset:
    await get_project(session, project_id)

    filename = file.filename or "upload.tif"
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Only GeoTIFF files (.tif/.tiff) are accepted")

    dest_dir = project_dir(settings, "uploads", project_id)
    dest = dest_dir / unique_name(filename)

    size = 0
    try:
        async with await anyio.open_file(dest, "wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds size limit")
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

    dataset = Dataset(
        project_id=project_id,
        filename=filename,
        path=str(dest),
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
    Path(dataset.path).unlink(missing_ok=True)
    await session.delete(dataset)
    await session.commit()
