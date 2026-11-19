"""Project-scoped multi-temporal scene registration endpoints."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import anyio
from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from ..models import Dataset, Scene
from ..schemas import SceneOut, SceneSpatialOut
from ..services.raster_service import RasterError, extract_scene_metadata
from ..services.schema_service import build_band_schema
from ..services.raster_preview import PreviewError, inspect_raster_pixel, render_raster_preview
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
    band_names: str | None = Form(default=None),
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

    # Optional explicit band names: a product whose bands are undescribed cannot
    # otherwise prove its band identity, and a band-count match is not identity.
    named_bands = None
    if band_names:
        named_bands = [token.strip() for token in band_names.split(",")]
        if not all(named_bands):
            raise HTTPException(status_code=422, detail="band_names must not contain empty entries")
    polarizations = None
    if polarization:
        polarizations = sorted({token.strip().upper() for token in polarization.split(",") if token.strip()})
        if not polarizations or not set(polarizations).issubset(POLARIZATIONS):
            raise HTTPException(status_code=422, detail="Polarization must contain VV, VH, HH, and/or HV")
    if sensor == "Sentinel-2" and polarizations:
        raise HTTPException(status_code=422, detail="Polarization is Sentinel-1 metadata")
    if sensor == "Sentinel-2" and acquisition_mode:
        raise HTTPException(status_code=422, detail="Acquisition mode is Sentinel-1 metadata")
    # STAC sat:orbit_state and sat:relative_orbit are defined for both
    # Sentinel constellations, so orbit direction/number are valid S2 metadata.
    if sensor == "Sentinel-1" and native_resolution:
        raise HTTPException(status_code=422, detail="Native spectral band resolutions are Sentinel-2 metadata")

    destination = (project_dir(settings, "uploads", project_id) / unique_name(filename)).resolve()
    size = 0
    digest = hashlib.sha256()
    try:
        async with await anyio.open_file(destination, "wb") as output:
            while chunk := await file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured size limit")
                digest.update(chunk)
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

    if named_bands is not None:
        if len(named_bands) != raster_metadata["band_count"]:
            destination.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"band_names lists {len(named_bands)} names but the raster has "
                    f"{raster_metadata['band_count']} bands"
                ),
            )
        raster_metadata["band_names"] = named_bands

    schema_names = named_bands or raster_metadata.get("band_names")
    schema_source = "request" if named_bands is not None else "scene-band-descriptions"
    if (
        not schema_names
        or len(schema_names) != raster_metadata["band_count"]
        or not all(isinstance(name, str) and name.strip() for name in schema_names)
    ):
        if polarizations and len(polarizations) == raster_metadata["band_count"]:
            schema_names = polarizations
            schema_source = "scene-polarization"
        else:
            schema_names = None
            schema_source = "scene-raster-metadata"

    scene = Scene(
        project_id=project_id,
        acquisition_datetime=acquired,
        platform=platform.strip() if platform and platform.strip() else None,
        sensor=sensor,
        product_type=product_type,
        product_level=product_level,
        source_filename=filename,
        storage_path=str(destination),
        content_sha256=digest.hexdigest(),
        size_bytes=size,
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
    nodata_values = raster_metadata["nodata_values"]
    dataset_nodata = (
        nodata_values[0]
        if nodata_values and all(value == nodata_values[0] for value in nodata_values)
        else None
    )
    active_learning_dataset = Dataset(
        project_id=project_id,
        filename=filename,
        path=str(destination),
        crs=raster_metadata["crs"],
        transform=raster_metadata["transform"],
        width=raster_metadata["width"],
        height=raster_metadata["height"],
        bands=raster_metadata["band_count"],
        dtype=raster_metadata["band_dtypes"][0],
        nodata=dataset_nodata,
        bounds=raster_metadata["bounds"],
        band_schema=build_band_schema(
            band_count=raster_metadata["band_count"],
            band_names=schema_names,
            sensor=sensor,
            source=schema_source,
        ),
        content_sha256=digest.hexdigest(),
        size_bytes=size,
    )
    # A scene also becomes a queryable raster dataset. Both records intentionally
    # reference the same immutable upload; deletion checks the remaining owner.
    session.add(scene)
    session.add(active_learning_dataset)
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


@router.get("/{scene_id}/file")
async def scene_file(project_id: int, scene_id: int, session: SessionDep) -> FileResponse:
    await get_project(session, project_id)
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id or not Path(scene.storage_path).is_file():
        raise HTTPException(404, "Scene file not found in this project")
    return FileResponse(scene.storage_path, media_type="image/tiff", filename=scene.source_filename)


@router.get("/{scene_id}/preview")
async def preview_scene_file(
    project_id: int,
    scene_id: int,
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
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id or not Path(scene.storage_path).is_file():
        raise HTTPException(404, "Scene file not found in this project")
    coordinates = (x0, y0, x1, y1)
    if any(value is not None for value in coordinates) and not all(value is not None for value in coordinates):
        raise HTTPException(status_code=422, detail="A preview window must provide x0, y0, x1, and y1")
    window = tuple(coordinates) if all(value is not None for value in coordinates) else None
    names = scene.band_names
    try:
        png = await anyio.to_thread.run_sync(
            lambda: render_raster_preview(scene.storage_path, mode=mode, size=size, names=names, window=window, upscale=upscale)
        )
    except PreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=60"})


@router.get("/{scene_id}/pixel")
async def inspect_scene_pixel(
    project_id: int,
    scene_id: int,
    session: SessionDep,
    x: int = Query(ge=0),
    y: int = Query(ge=0),
    mode: str = "true-color",
) -> dict:
    """GDAL pixel-probe fallback for TIFFs the browser decoder cannot inspect."""
    await get_project(session, project_id)
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id or not Path(scene.storage_path).is_file():
        raise HTTPException(404, "Scene file not found in this project")
    try:
        return await anyio.to_thread.run_sync(
            lambda: inspect_raster_pixel(scene.storage_path, x=x, y=y, mode=mode, names=scene.band_names)
        )
    except PreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    dataset_reference = await session.execute(
        select(Dataset.id).where(Dataset.path == str(source_path)).limit(1)
    )
    scene_reference = await session.execute(
        select(Scene.id).where(Scene.storage_path == str(source_path)).limit(1)
    )
    if dataset_reference.scalar_one_or_none() is None and scene_reference.scalar_one_or_none() is None:
        source_path.unlink(missing_ok=True)
    return Response(status_code=204)
