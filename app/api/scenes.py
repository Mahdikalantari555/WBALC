"""Project-scoped multi-temporal scene registration endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import anyio
from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from ..models import Scene
from ..schemas import SceneOut, SceneSpatialOut
from ..services.raster_service import RasterError, extract_scene_metadata
from ..storage import project_dir, unique_name
from .deps import SessionDep, SettingsDep, get_project

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["scenes"])
ALLOWED_SUFFIXES = {".tif", ".tiff"}
CHUNK_BYTES = 1024 * 1024
SENSORS = {"Sentinel-1", "Sentinel-2"}
POLARIZATIONS = {"VV", "VH", "HH", "HV"}


def _parse_json_object(value: str | None, field: str) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail=f"{field} must be a JSON object")
    return parsed


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="acquisition_datetime must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="acquisition_datetime must include a timezone offset (for example, Z)")
    return parsed.astimezone(timezone.utc)


def _scene_out(scene: Scene, settings) -> SceneOut:
    values = {
        name: getattr(scene, name)
        for name in SceneOut.model_fields
        if hasattr(scene, name)
    }
    path = Path(scene.storage_path)
    try:
        reference = str(path.relative_to(settings.storage_dir.resolve()))
    except ValueError:
        reference = path.name
    for field in ("acquisition_datetime", "uploaded_at", "registered_at"):
        timestamp = values.get(field)
        if timestamp is not None and timestamp.tzinfo is None:
            # SQLite omits offsets for DateTime(timezone=True); stored acquisition times are UTC.
            values[field] = timestamp.replace(tzinfo=timezone.utc)
    values.update(
        storage_reference=reference,
        size_bytes=path.stat().st_size if path.exists() else 0,
    )
    return SceneOut.model_validate(values)


def _grid_dict(scene: Scene) -> dict:
    return {
        "crs": scene.crs,
        "transform": scene.transform,
        "width": scene.width,
        "height": scene.height,
        "pixel_size": [scene.pixel_size_x, scene.pixel_size_y],
        "resolution": [scene.resolution_x, scene.resolution_y],
        "bounds": scene.bounds,
    }


@router.post("", response_model=SceneOut, status_code=201)
async def register_scene(
    project_id: int,
    file: UploadFile,
    session: SessionDep,
    settings: SettingsDep,
    sensor: Literal["Sentinel-1", "Sentinel-2"] = Form(...),
    acquisition_datetime: str | None = Form(default=None),
    platform: str | None = Form(default=None, max_length=100),
    product_type: str | None = Form(default=None, max_length=100),
    product_level: str | None = Form(default=None, max_length=50),
    polarization: str | None = Form(default=None),
    acquisition_mode: str | None = Form(default=None, max_length=30),
    orbit_direction: Literal["ascending", "descending"] | None = Form(default=None),
    relative_orbit: int | None = Form(default=None, ge=1, le=999),
    processing_baseline: str | None = Form(default=None, max_length=50),
    native_band_resolutions: str | None = Form(default=None),
    acquisition_metadata: str | None = Form(default=None),
    product_metadata: str | None = Form(default=None),
) -> SceneOut:
    await get_project(session, project_id)
    filename = file.filename or "upload.tif"
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Only GeoTIFF files (.tif/.tiff) are accepted")

    acquired = _parse_datetime(acquisition_datetime)
    acquisition_json = _parse_json_object(acquisition_metadata, "acquisition_metadata")
    product_json = _parse_json_object(product_metadata, "product_metadata")
    native_resolution = _parse_json_object(native_band_resolutions, "native_band_resolutions")
    if native_resolution is not None:
        try:
            native_resolution = {str(k): float(v) for k, v in native_resolution.items()}
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="native_band_resolutions values must be numbers") from exc
        if any(value <= 0 for value in native_resolution.values()):
            raise HTTPException(status_code=422, detail="native band resolutions must be positive")

    polarizations = None
    if polarization:
        polarizations = sorted({token.strip().upper() for token in polarization.split(",") if token.strip()})
        if not polarizations or not set(polarizations).issubset(POLARIZATIONS):
            raise HTTPException(status_code=422, detail="Polarization must contain VV, VH, HH, and/or HV")
    if sensor == "Sentinel-2" and polarizations:
        raise HTTPException(status_code=422, detail="Polarization is Sentinel-1 metadata")
    if sensor == "Sentinel-2" and (acquisition_mode or orbit_direction or relative_orbit is not None):
        raise HTTPException(status_code=422, detail="Acquisition mode and orbit fields are Sentinel-1 metadata")
    if sensor == "Sentinel-1" and native_resolution:
        raise HTTPException(status_code=422, detail="Native spectral band resolutions are Sentinel-2 metadata")

    destination = (project_dir(settings, "uploads", project_id) / unique_name(filename)).resolve()
    size = 0
    try:
        async with await anyio.open_file(destination, "wb") as output:
            while chunk := await file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured size limit")
                await output.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Uploaded GeoTIFF is empty")
    try:
        raster_metadata = await anyio.to_thread.run_sync(extract_scene_metadata, destination)
    except RasterError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scene = Scene(
        project_id=project_id,
        acquisition_datetime=acquired,
        platform=platform.strip() if platform and platform.strip() else None,
        sensor=sensor,
        product_type=product_type,
        product_level=product_level,
        source_filename=filename,
        storage_path=str(destination),
        polarization=polarizations,
        acquisition_mode=acquisition_mode,
        orbit_direction=orbit_direction,
        relative_orbit=relative_orbit,
        processing_baseline=processing_baseline,
        native_band_resolutions=native_resolution,
        acquisition_metadata=acquisition_json,
        product_metadata=product_json,
        uploaded_at=datetime.now(timezone.utc),
        **raster_metadata,
    )
    session.add(scene)
    try:
        await session.commit()
        await session.refresh(scene)
    except Exception:
        await session.rollback()
        destination.unlink(missing_ok=True)
        raise
    return _scene_out(scene, settings)


@router.get("", response_model=list[SceneOut])
async def list_scenes(project_id: int, session: SessionDep, settings: SettingsDep) -> list[SceneOut]:
    await get_project(session, project_id)
    result = await session.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(
            Scene.acquisition_datetime.is_(None),
            Scene.acquisition_datetime.desc(),
            Scene.registered_at.desc(),
            Scene.id.desc(),
        )
    )
    return [_scene_out(scene, settings) for scene in result.scalars()]


@router.get("/{scene_id}", response_model=SceneOut)
async def get_scene(project_id: int, scene_id: int, session: SessionDep, settings: SettingsDep) -> SceneOut:
    await get_project(session, project_id)
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found in project {project_id}")
    return _scene_out(scene, settings)


@router.get("/{scene_id}/spatial", response_model=SceneSpatialOut)
async def scene_spatial_metadata(project_id: int, scene_id: int, session: SessionDep) -> SceneSpatialOut:
    await get_project(session, project_id)
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found in project {project_id}")
    return SceneSpatialOut(
        scene_id=scene.id,
        crs=scene.crs,
        transform=scene.transform,
        bounds=scene.bounds,
        width=scene.width,
        height=scene.height,
        pixel_size_x=scene.pixel_size_x,
        pixel_size_y=scene.pixel_size_y,
        resolution_x=scene.resolution_x,
        resolution_y=scene.resolution_y,
        has_validity_mask=scene.has_validity_mask,
        nodata_values=scene.nodata_values,
        grid=_grid_dict(scene),
    )


@router.delete("/{scene_id}", status_code=204)
async def delete_scene(project_id: int, scene_id: int, session: SessionDep) -> Response:
    await get_project(session, project_id)
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found in project {project_id}")
    source_path = Path(scene.storage_path)
    await session.delete(scene)
    await session.commit()
    source_path.unlink(missing_ok=True)
    return Response(status_code=204)
