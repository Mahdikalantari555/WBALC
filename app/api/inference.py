"""Inference & GeoTIFF export endpoints (inference-export capability)."""

from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path

import anyio
import numpy as np
import rasterio
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select

from ..models import Dataset, Export
from ..schemas import (
    ExportOut,
    MapFieldOut,
    MapGridOut,
    PredictRequest,
    PredictResponse,
    Region,
)
from ..services.al_service import UNCERTAINTY_METHODS
from ..services.inference_service import (
    class_colors,
    export_hard_cells_geotiff,
    export_hard_geotiff,
    export_probability_cells_geotiff,
    export_probability_geotiff,
    export_uncertainty_cells_geotiff,
    export_uncertainty_geotiff,
    grid_metadata,
    maps_from_inference,
    pixel_transform,
    uncertainty_colors,
    validate_export_grid,
)
from ..services.pipeline import checkpoint_or_409
from ..services.raster_service import (
    RasterError,
    load_raster,
    make_grid,
    patch_features,
    patch_validity,
)
from ..services.training_service import align_probabilities
from ..storage import project_dir
from .deps import (
    SessionDep,
    SettingsDep,
    get_project,
    latest_run,
    require_dataset,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["inference"])

EXPORT_TYPES = {
    "hard": "hard",
    "probability": "probability",
    "prob": "probability",
    "uncertainty": "uncertainty",
    "som": "som",
}
DEFAULT_UNCERTAINTY_METHOD = "entropy"


def _check_method(method: str) -> str:
    if method not in UNCERTAINTY_METHODS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown uncertainty method '{method}'; "
                f"use one of {', '.join(UNCERTAINTY_METHODS)}"
            ),
        )
    return method


async def _run_inference(
    session,
    settings,
    project,
    dataset: Dataset,
    region: Region | None,
    iteration: int | None,
    method: str = DEFAULT_UNCERTAINTY_METHOD,
    persist: bool = True,
):
    """Infer a dataset (or region) and, unless `persist` is False, export it.

    Read-only consumers (map layers, PNG/CSV previews) pass `persist=False`: they
    only need the arrays, and writing a GeoTIFF per request would fill the export
    table with duplicates of the same run.
    """
    run = await latest_run(session, project.id, iteration)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail="No trained model found; submit labels and POST /train first",
        )
    checkpoint = checkpoint_or_409(run)
    if checkpoint["bands"] != dataset.bands:
        raise HTTPException(
            status_code=409,
            detail=f"Model expects {checkpoint['bands']} bands but dataset has {dataset.bands}",
        )

    if region is None:
        region = Region(x0=0, y0=0, x1=dataset.width, y1=dataset.height)
    if not (0 <= region.x0 < region.x1 <= dataset.width and 0 <= region.y0 < region.y1 <= dataset.height):
        raise HTTPException(
            status_code=422,
            detail=f"Region {region.model_dump()} outside dataset bounds {dataset.width}x{dataset.height}",
        )

    resolution = checkpoint.get("resolution", "patch")
    patch_size, stride = (
        (1, 1) if resolution == "pixel" else (checkpoint["patch_size"], checkpoint["stride"])
    )
    region_h, region_w = region.y1 - region.y0, region.x1 - region.x0

    def _compute():
        model = checkpoint["model"]
        if resolution == "pixel":
            from ..services.raster_service import pixel_features

            h, w = region_h, region_w
            grid = make_grid(h, w, 1, 1)
            with rasterio.open(dataset.path) as src:
                if src.count * src.width * src.height > settings.max_raster_elements:
                    raise RasterError(
                        f"Raster exceeds configured processing limit "
                        f"({src.count}x{src.height}x{src.width})"
                    )
                k = len(run.classes)
                probability_cube = np.zeros((k, h, w), dtype=np.float32)
                valid = np.zeros((h, w), dtype=bool)
                for y0 in range(0, h, 256):
                    for x0 in range(0, w, 256):
                        bh, bw = min(256, h - y0), min(256, w - x0)
                        window = rasterio.windows.Window(region.x0 + x0, region.y0 + y0, bw, bh)
                        block = src.read(window=window, masked=True, out_dtype="float32").filled(np.nan)
                        X_block, valid_block = pixel_features(block)
                        raw_block = np.asarray(model.predict_proba(X_block))
                        model_classes = [run.classes[int(c)] for c in model.classes_]
                        aligned = align_probabilities(raw_block, model_classes, run.classes)
                        probability_cube[:, y0:y0 + bh, x0:x0 + bw] = aligned.T.reshape(k, bh, bw)
                        valid[y0:y0 + bh, x0:x0 + bw] = valid_block.reshape(bh, bw)
                valid = valid.reshape(-1)
                probs = np.moveaxis(probability_cube, 0, -1).reshape(h * w, k)
        else:
            arr = load_raster(dataset.path, dataset.nodata, settings.max_raster_elements)
            crop = arr[:, region.y0 : region.y1, region.x0 : region.x1]
            grid = make_grid(crop.shape[1], crop.shape[2], patch_size, stride)
            X = patch_features(crop, grid)
            valid = patch_validity(crop, grid)
            raw = np.asarray(model.predict_proba(X))
            model_classes = [run.classes[int(c)] for c in model.classes_]
            probs = align_probabilities(raw, model_classes, run.classes)
        hard, prob, unc = maps_from_inference(probs, valid, grid.shape, method)
        return grid, valid, hard, prob, unc

    try:
        grid, valid, hard, prob, unc = await anyio.to_thread.run_sync(_compute)
    except RasterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    meta = grid_metadata(
        grid, region.x0, region.y0, stride, include_cells=resolution != "pixel"
    )
    meta["resolution"] = "pixel" if resolution == "pixel" else "patch-cells"
    meta["method"] = method
    if not persist:
        return run, region, grid, valid, hard, prob, unc, patch_size, stride, resolution

    # A classified raster without georeferencing is not usable data, and writing
    # an identity transform would present a made-up location. Refuse explicitly.
    if not dataset.crs:
        raise HTTPException(
            status_code=422,
            detail=(
                "Dataset has no CRS: refusing to write a GeoTIFF export that would "
                "claim a georeference it does not have. Upload a georeferenced "
                "raster to export maps (map layers and CSV stay available)."
            ),
        )

    export_dir = project_dir(settings, "exports", project.id)
    tag = f"ds{dataset.id}_iter{run.iteration}_{uuid.uuid4().hex[:8]}"
    hard_path = export_dir / f"hard_{tag}.tif"
    prob_path = export_dir / f"probability_{tag}.tif"
    unc_path = export_dir / f"uncertainty_{method}_{tag}.tif"

    if resolution == "pixel":
        # One value per source pixel on the window's exact affine.
        transform = pixel_transform(dataset.transform, region.x0, region.y0)
        writers = (
            lambda: export_hard_geotiff(
                hard_path, hard, run.classes, dataset.crs, transform, meta, resolution="pixel"
            ),
            lambda: export_probability_geotiff(
                prob_path, prob, run.classes, dataset.crs, transform, meta,
                valid=valid, resolution="pixel",
            ),
            lambda: export_uncertainty_geotiff(
                unc_path, unc, run.classes, dataset.crs, transform, method, meta,
                resolution="pixel",
            ),
        )
    else:
        # One value per patch cell, painted over the cell's true pixel window.
        transform = pixel_transform(dataset.transform, region.x0, region.y0)
        writers = (
            lambda: export_hard_cells_geotiff(
                hard_path, hard, valid.reshape(grid.shape), grid, run.classes,
                dataset.crs, transform, region_h, region_w, meta,
            ),
            lambda: export_probability_cells_geotiff(
                prob_path, prob, valid.reshape(grid.shape), grid, run.classes,
                dataset.crs, transform, region_h, region_w, meta,
            ),
            lambda: export_uncertainty_cells_geotiff(
                unc_path, unc, valid.reshape(grid.shape), grid, run.classes,
                dataset.crs, transform, method, region_h, region_w, meta,
            ),
        )

    for write in writers:
        await anyio.to_thread.run_sync(write)

    def _validate_exports():
        validate_export_grid(
            dataset.path, (hard_path, prob_path, unc_path), (region.x0, region.y0, region_w, region_h)
        )

    try:
        await anyio.to_thread.run_sync(_validate_exports)
    except RasterError as exc:
        for failed_path in (hard_path, prob_path, unc_path):
            Path(failed_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Export grid validation failed: {exc}") from exc
    except Exception as exc:  # unreadable/incomplete artifact
        for failed_path in (hard_path, prob_path, unc_path):
            Path(failed_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Export could not be verified: {exc}") from exc

    for etype, path in (("hard", hard_path), ("probability", prob_path), ("uncertainty", unc_path)):
        session.add(
            Export(
                project_id=project.id,
                dataset_id=dataset.id,
                training_run_id=run.id,
                type=etype,
                path=str(path),
                region={**region.model_dump(), "method": method} if etype == "uncertainty" else region.model_dump(),
            )
        )
    await session.commit()
    return run, region, grid, valid, hard, prob, unc, patch_size, stride, resolution


@router.post("/predict", response_model=PredictResponse)
async def predict(
    project_id: int,
    payload: PredictRequest,
    session: SessionDep,
    settings: SettingsDep,
    method: str = Query(default=DEFAULT_UNCERTAINTY_METHOD),
):
    """Run inference on the whole image or a pixel region.

    Returns patch-grid classification, probability and uncertainty maps (all
    three are also exported as GeoTIFF; see `exports` for download URLs).
    """
    _check_method(method)
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, payload.dataset_id)
    (
        run, region, grid, valid, hard, prob, unc, patch_size, stride, resolution
    ) = await _run_inference(
        session, settings, project, dataset, payload.region, payload.iteration, method
    )
    shape = grid.shape
    valid_grid = valid.reshape(shape)
    unc_json = [
        [None if not valid_grid[r, c] else round(float(unc[r, c]), 6) for c in range(shape[1])]
        for r in range(shape[0])
    ]
    prob_json = [
        [
            [
                None if not valid_grid[r, c] else round(float(band[r, c]), 6)
                for c in range(shape[1])
            ]
            for r in range(shape[0])
        ]
        for band in prob
    ]
    return PredictResponse(
        project_id=project.id,
        dataset_id=dataset.id,
        model_iteration=run.iteration,
        classes=run.classes,
        resolution=resolution,
        region=region,
        grid_shape=list(shape),
        patch_size=patch_size,
        stride=stride,
        hard_map=hard.tolist() if payload.include_maps else None,
        probability_map=prob_json if payload.include_maps else None,
        uncertainty_map=unc_json if payload.include_maps else None,
        uncertainty_method=method if payload.include_maps else None,
        valid_map=valid_grid.tolist() if payload.include_maps else None,
        exports={
            "hard": f"/projects/{project.id}/download/hard",
            "probability": f"/projects/{project.id}/download/probability",
            "uncertainty": f"/projects/{project.id}/download/uncertainty?method={method}",
        },
    )


@router.get("/predict/map", response_model=MapFieldOut)
async def predict_map(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    layer: str = Query(default="hard", pattern="^(hard|uncertainty)$"),
    method: str = Query(default=DEFAULT_UNCERTAINTY_METHOD),
    dataset_id: int | None = Query(default=None),
    iteration: int | None = Query(default=None, ge=0),
):
    """One grid-aligned field for the map layers.

    Returns only what a map needs (values + validity + grid geometry), never the
    full class-probability tensor, and reports whether a newer training run
    exists than the one the field came from.
    """
    _check_method(method)
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, dataset_id)
    (
        run, region, grid, valid, hard, _prob, unc, patch_size, stride, resolution
    ) = await _run_inference(
        session, settings, project, dataset, None, iteration, method, persist=False
    )
    latest = await latest_run(session, project.id)
    shape = grid.shape
    valid_grid = valid.reshape(shape)

    if layer == "hard":
        values: list[list[int | float | None]] = [
            [None if not valid_grid[r, c] else int(hard[r, c]) for c in range(shape[1])]
            for r in range(shape[0])
        ]
        vmin, vmax = 0.0, float(max(0, len(run.classes) - 1))
    else:
        clean = np.where(np.isfinite(unc), unc, np.nan)
        values = [
            [None if not valid_grid[r, c] else round(float(clean[r, c]), 6) for c in range(shape[1])]
            for r in range(shape[0])
        ]
        finite = clean[np.isfinite(clean)]
        vmin = float(finite.min()) if finite.size else 0.0
        vmax = float(finite.max()) if finite.size else 1.0

    return MapFieldOut(
        layer=layer,
        method=method if layer == "uncertainty" else None,
        project_id=project.id,
        dataset_id=dataset.id,
        model_iteration=run.iteration,
        training_run_id=run.id,
        classes=run.classes,
        resolution=resolution,
        grid=MapGridOut(
            rows=shape[0],
            cols=shape[1],
            patch_size=patch_size,
            stride=stride,
            region=region,
        ),
        values=values,
        valid=valid_grid.tolist(),
        min=vmin,
        max=vmax,
        stale=bool(latest is not None and latest.id != run.id),
        exports={
            "hard": f"/projects/{project.id}/download/hard?dataset_id={dataset.id}",
            "probability": f"/projects/{project.id}/download/probability?dataset_id={dataset.id}",
            "uncertainty": (
                f"/projects/{project.id}/download/uncertainty?dataset_id={dataset.id}&method={method}"
            ),
        },
    )


def _exports_for(project_id: int, dataset_id: int | None = None, method: str | None = None):
    """Latest exports by type, newest first, filtered by dataset/method."""
    stmt = select(Export).where(Export.project_id == project_id).order_by(Export.id.desc())
    if dataset_id is not None:
        stmt = stmt.where(Export.dataset_id == dataset_id)
    return stmt


async def _latest_export(session, project_id, etype, dataset_id=None, method=None):
    stmt = _exports_for(project_id, dataset_id)
    stmt = stmt.where(Export.type == etype)
    exports = list((await session.execute(stmt)).scalars())
    for export in exports:
        if not Path(export.path).exists():
            continue
        if method and export.type == "uncertainty":
            stored = (export.region or {}).get("method")
            if stored and stored != method:
                continue
        return export
    return None


@router.get("/download/{export_type}")
async def download(
    project_id: int,
    export_type: str,
    session: SessionDep,
    settings: SettingsDep,
    dataset_id: int | None = Query(default=None),
    method: str = Query(default=DEFAULT_UNCERTAINTY_METHOD),
):
    """Download the latest GeoTIFF export of the given type.

    Types: `hard` (class indices + colormap), `probability` (one band per class),
    `uncertainty` (0..1 float, nodata for invalid patches). If no export exists
    yet but a model is trained, inference runs automatically.
    """
    project = await get_project(session, project_id)
    if export_type not in EXPORT_TYPES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown export type '{export_type}'; use hard, probability, "
                "uncertainty or som"
            ),
        )
    etype = EXPORT_TYPES[export_type]
    if etype == "uncertainty":
        _check_method(method)

    export = await _latest_export(session, project_id, etype, dataset_id, method)
    latest = await latest_run(session, project_id)
    stale = bool(
        export is not None
        and latest is not None
        and etype != "som"
        and export.training_run_id != latest.id
    )

    if export is None or stale:
        dataset = await require_dataset(session, project_id, dataset_id)
        if etype == "som":
            from ..schemas import SomClassifyRequest
            from .som import run_som_classification

            export, _, _ = await run_som_classification(
                session, settings, project, dataset, SomClassifyRequest(dataset_id=dataset.id)
            )
        else:
            # A newer run exists than the artifact on disk: re-running inference
            # is the only way to hand back the model the user just trained.
            # `_latest_export` filters by method so uncertainty artifacts of a
            # different method are never substituted.
            await _run_inference(session, settings, project, dataset, None, None, method)
            export = await _latest_export(session, project_id, etype, dataset.id, method)
            if export is None:
                raise HTTPException(status_code=500, detail="Export failed")
            stale = False

    suffix = f"_{method}" if etype == "uncertainty" else ""
    iteration = None
    if export.training_run_id is not None:
        from ..models import TrainingRun

        run = await session.get(TrainingRun, export.training_run_id)
        iteration = run.iteration if run is not None else None
    headers = {
        "X-RSAL-Export-Stale": "true" if stale else "false",
        "X-RSAL-Model-Iteration": str(iteration) if iteration is not None else "",
    }
    return FileResponse(
        export.path,
        media_type="image/tiff",
        filename=f"project_{project_id}_{etype}{suffix}_ds{export.dataset_id}.tif",
        headers=headers,
    )


@router.get("/exports/{export_type}.png")
async def download_png(
    project_id: int,
    export_type: str,
    session: SessionDep,
    settings: SettingsDep,
    dataset_id: int | None = Query(default=None),
    method: str = Query(default=DEFAULT_UNCERTAINTY_METHOD),
    scale: int = Query(default=8, ge=1, le=32, description="Pixels per grid cell"),
):
    """PNG snapshot of a layer, painted with the same colours the map uses."""
    if export_type not in ("hard", "uncertainty"):
        raise HTTPException(
            status_code=404,
            detail=f"PNG export supports hard and uncertainty; '{export_type}' has no palette",
        )
    if export_type == "uncertainty":
        _check_method(method)
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, dataset_id)
    (
        run, _region, grid, valid, hard, _prob, unc, _patch, _stride, _res
    ) = await _run_inference(
        session, settings, project, dataset, None, None, method, persist=False
    )
    palette = class_colors(len(run.classes))
    shape = grid.shape
    valid_grid = valid.reshape(shape)
    unc_rgb = uncertainty_colors(unc) if export_type == "uncertainty" else None

    def _paint() -> bytes:
        cells = np.zeros((shape[0] * scale, shape[1] * scale, 4), dtype=np.uint8)
        for r in range(shape[0]):
            for c in range(shape[1]):
                if not valid_grid[r, c]:
                    continue  # transparent
                if export_type == "hard":
                    rgb = palette[int(hard[r, c]) % len(palette)]
                else:
                    # Same ramp and same relative stretch as the map overlay.
                    rgb = tuple(int(v) for v in unc_rgb[r, c])
                cells[r * scale : (r + 1) * scale, c * scale : (c + 1) * scale, :3] = rgb
                cells[r * scale : (r + 1) * scale, c * scale : (c + 1) * scale, 3] = 255
        from PIL import Image

        buffer = io.BytesIO()
        Image.fromarray(cells, mode="RGBA").save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    png = await anyio.to_thread.run_sync(_paint)
    suffix = f"_{method}" if export_type == "uncertainty" else ""
    return StreamingResponse(
        io.BytesIO(png),
        media_type="image/png",
        headers={
            "content-disposition": (
                f'attachment; filename="project_{project_id}_{export_type}{suffix}.png"'
            ),
            "X-RSAL-Model-Iteration": str(run.iteration),
        },
    )


@router.get("/exports/{export_type}.csv")
async def download_csv(
    project_id: int,
    export_type: str,
    session: SessionDep,
    settings: SettingsDep,
    dataset_id: int | None = Query(default=None),
    method: str = Query(default=DEFAULT_UNCERTAINTY_METHOD),
):
    """Per-cell table: row, col, pixel window, class, uncertainty, validity."""
    if export_type not in ("hard", "uncertainty"):
        raise HTTPException(
            status_code=404,
            detail=f"CSV export supports hard and uncertainty; got '{export_type}'",
        )
    if export_type == "uncertainty":
        _check_method(method)
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, dataset_id)
    (
        run, region, grid, valid, hard, _prob, unc, _patch, _stride, _res
    ) = await _run_inference(
        session, settings, project, dataset, None, None, method, persist=False
    )
    shape = grid.shape
    valid_grid = valid.reshape(shape)

    def _rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "row",
                "col",
                "x0",
                "y0",
                "x1",
                "y1",
                "valid",
                "class_index",
                "class_name",
                "uncertainty",
                "iteration",
                "method",
            ]
        )
        for r in range(shape[0]):
            for c in range(shape[1]):
                x0, y0 = grid.xs[c] + region.x0, grid.ys[r] + region.y0
                x1, y1 = x0 + grid.patch_w, y0 + grid.patch_h
                if not valid_grid[r, c]:
                    writer.writerow([r, c, x0, y0, x1, y1, "false", "", "", "", run.iteration, method])
                    continue
                index = int(hard[r, c])
                value = float(unc[r, c])
                writer.writerow(
                    [
                        r,
                        c,
                        x0,
                        y0,
                        x1,
                        y1,
                        "true",
                        index,
                        run.classes[index] if index < len(run.classes) else "",
                        f"{value:.6f}" if np.isfinite(value) else "",
                        run.iteration,
                        method,
                    ]
                )
        buffer.seek(0)
        return buffer

    buffer = await anyio.to_thread.run_sync(_rows)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "content-disposition": f'attachment; filename="project_{project_id}_{export_type}.csv"'
        },
    )


@router.get("/exports", response_model=list[ExportOut])
async def list_exports(
    project_id: int,
    session: SessionDep,
    dataset_id: int | None = Query(default=None),
):
    """Every export of the project, annotated with iteration, staleness and dataset."""
    from ..models import Dataset, TrainingRun

    await get_project(session, project_id)
    stmt = select(Export).where(Export.project_id == project_id).order_by(Export.id)
    if dataset_id is not None:
        stmt = stmt.where(Export.dataset_id == dataset_id)
    exports = list((await session.execute(stmt)).scalars())
    if not exports:
        return []
    # One row per artifact: the newest export of each (dataset, type, method).
    newest: dict[tuple[int, str, str | None], Export] = {}
    for export in exports:
        key = (export.dataset_id, export.type, (export.region or {}).get("method"))
        newest[key] = export
    exports = sorted(newest.values(), key=lambda e: e.id)

    latest = await latest_run(session, project_id)
    runs = {
        run.id: run.iteration
        for run in (
            await session.execute(
                select(TrainingRun).where(TrainingRun.project_id == project_id)
            )
        ).scalars()
    }
    names = {
        d.id: d.filename
        for d in (
            await session.execute(select(Dataset).where(Dataset.project_id == project_id))
        ).scalars()
    }
    return [
        ExportOut(
            id=e.id,
            project_id=e.project_id,
            dataset_id=e.dataset_id,
            training_run_id=e.training_run_id,
            type=e.type,
            region=e.region,
            created_at=e.created_at,
            iteration=runs.get(e.training_run_id),
            method=(e.region or {}).get("method"),
            stale=bool(latest is not None and latest.id != e.training_run_id),
            dataset_name=names.get(e.dataset_id),
        )
        for e in exports
    ]


@router.get("/legends/classes")
async def class_legend(project_id: int, session: SessionDep):
    """Class colours, so a client never has to guess or hard-code them."""
    project = await get_project(session, project_id)
    return {
        "classes": [
            {"index": i, "name": name, "color": color}
            for i, (name, color) in enumerate(zip(project.classes, (c for c in _class_hex(len(project.classes)))))
        ]
    }


def _class_hex(n: int) -> list[str]:
    from ..services.inference_service import CLASS_PALETTE

    return [CLASS_PALETTE[i % len(CLASS_PALETTE)] for i in range(n)]
