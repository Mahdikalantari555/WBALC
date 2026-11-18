"""Self-Organizing Map (SOM) exploration & unsupervised classification endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
import numpy as np
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..models import Dataset, Export, Project
from ..schemas import (
    Region,
    SomCell,
    SomClassifyRequest,
    SomClassifyResponse,
    SomClusterSummary,
    SomRequest,
    SomResponse,
)
from ..services.al_service import uncertainty_scores
from ..services.inference_service import (
    export_som_geotiff,
    grid_metadata,
    pixel_transform,
    validate_export_grid,
)
from ..services.label_service import build_training_targets
from ..services.pipeline import checkpoint_or_409
from ..services.raster_service import (
    RasterError,
    load_raster,
    make_grid,
    patch_features,
    patch_validity,
    sample_id,
)
from ..services.som_service import (
    UnsupervisedSomResult,
    classify_unsupervised_som,
    fit_som,
    normalized_band_profiles,
)
from ..services.training_service import align_probabilities
from ..storage import project_dir
from .deps import (
    SessionDep,
    SettingsDep,
    get_project,
    latest_run,
    project_labels,
    require_dataset,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["self-organizing-map"])


async def _run_som(
    project_id: int,
    payload: SomRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> SomResponse:
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, payload.dataset_id)

    run = await latest_run(session, project_id)
    checkpoint = None
    model_iteration: int | None = None
    model_note: str | None = None
    if run is not None and Path(run.checkpoint_path).exists():
        loaded = checkpoint_or_409(run)
        if loaded.get("bands") != dataset.bands:
            model_note = (
                f"Model expects {loaded['bands']} bands but dataset {dataset.id} has "
                f"{dataset.bands}; no supervised annotations are shown."
            )
        elif loaded.get("resolution") != "patch":
            # Patch embeddings cannot be scored by a pixel-feature model; saying so
            # is better than a 500 or a silently wrong overlay.
            model_note = (
                f"Latest model (iteration {run.iteration}) was trained at "
                f"{loaded.get('resolution')} resolution and cannot annotate patch "
                "cells; retrain with resolution='patch' to show predictions."
            )
        else:
            checkpoint = loaded
            model_iteration = run.iteration

    patch_size = payload.patch_size or (
        checkpoint["patch_size"] if checkpoint else settings.patch_size
    )
    stride = payload.stride or (
        checkpoint["stride"] if checkpoint else settings.resolved_stride()
    )
    grid = make_grid(dataset.height, dataset.width, patch_size, stride)

    labels = await project_labels(session, project_id)
    labeled_sids, labeled_targets, _ = build_training_targets(
        labels, {dataset.id: dataset}, dataset, {dataset.id: grid}, project.classes
    )
    label_by_sid = {
        sid: project.classes[target]
        for sid, target in zip(labeled_sids, labeled_targets)
    }

    n_rows, n_cols = grid.shape
    all_sids = [sample_id(dataset.id, r, c) for r in range(n_rows) for c in range(n_cols)]

    def _compute() -> SomResponse:
        arr = load_raster(dataset.path, dataset.nodata, settings.max_raster_elements)
        X_all = patch_features(arr, grid)
        valid = patch_validity(arr, grid)
        valid_idx = np.flatnonzero(valid)
        if valid_idx.size == 0:
            raise RasterError("Dataset contains no valid (non-nodata) patches to map")
        # Fit and summarise on valid patches only: an all-nodata patch has an
        # all-zero embedding that would otherwise dominate a neuron and be
        # offered as a review sample.
        X = X_all[valid_idx]
        som = fit_som(
            X,
            rows=payload.rows,
            cols=payload.cols,
            epochs=payload.epochs,
            sigma=payload.sigma,
            learning_rate=payload.learning_rate,
            random_state=settings.random_state,
        )
        band_means, band_profiles = normalized_band_profiles(X, som.weights_denorm, dataset.bands)

        probs = None
        pred_idx = None
        confs = None
        uncs = None
        if checkpoint is not None:
            model = checkpoint["model"]
            raw = np.asarray(model.predict_proba(X))
            model_classes = [project.classes[int(c)] for c in model.classes_]
            probs = align_probabilities(raw, model_classes, project.classes)
            pred_idx = np.argmax(probs, axis=1)
            confs = probs.max(axis=1)
            uncs = uncertainty_scores(probs, "entropy")

        # `som` was fitted on valid patches only, so its BMU indices are local to
        # `valid_idx`; the grid/sample ids need the global patch index.
        grouped: dict[int, list[int]] = {}
        for local_i, bmu in enumerate(som.bmus.tolist()):
            grouped.setdefault(int(bmu), []).append(local_i)

        class_rank = {c: idx for idx, c in enumerate(project.classes)}
        cells: list[SomCell] = []
        active_neurons = 0

        for r in range(som.rows):
            for c in range(som.cols):
                u = r * som.cols + c
                idxs = grouped.get(u, [])
                if idxs:
                    active_neurons += 1
                    idx_arr = np.asarray(idxs, dtype=np.int64)
                    order = np.argsort(som.bmu_dists[idx_arr], kind="stable")
                    ordered = [int(idx_arr[k]) for k in order]  # local (valid) indices
                    sids = [all_sids[int(valid_idx[k])] for k in ordered]
                    rep_sid = sids[0]
                    cell_qe = float(som.bmu_dists[idx_arr].mean())
                else:
                    ordered = []
                    sids = []
                    rep_sid = None
                    cell_qe = 0.0

                label_counts: dict[str, int] = {}
                for sid in sids:
                    cls = label_by_sid.get(sid)
                    if cls is not None:
                        label_counts[cls] = label_counts.get(cls, 0) + 1
                labeled_count = sum(label_counts.values())
                dominant_label = (
                    max(label_counts.keys(), key=lambda name: (label_counts[name], -class_rank.get(name, 999)))
                    if label_counts
                    else None
                )

                prediction_counts: dict[str, int] = {}
                predicted_class: str | None = None
                mean_conf: float | None = None
                mean_unc: float | None = None
                if probs is not None and ordered:
                    global_ordered = np.asarray(
                        [int(valid_idx[k]) for k in ordered], dtype=np.int64
                    )
                    for k in global_ordered:
                        cname = project.classes[int(pred_idx[k])]
                        prediction_counts[cname] = prediction_counts.get(cname, 0) + 1
                    predicted_class = max(
                        prediction_counts.keys(),
                        key=lambda name: (prediction_counts[name], -class_rank.get(name, 999)),
                    )
                    mean_conf = float(confs[global_ordered].mean())
                    mean_unc = float(uncs[global_ordered].mean())

                cells.append(
                    SomCell(
                        row=r,
                        col=c,
                        hit_count=len(sids),
                        labeled_count=labeled_count,
                        unlabeled_count=len(sids) - labeled_count,
                        u_value=float(som.u_matrix[r, c]),
                        quantization_error=cell_qe,
                        dominant_label=dominant_label,
                        label_counts=label_counts,
                        predicted_class=predicted_class,
                        prediction_counts=prediction_counts,
                        mean_confidence=mean_conf,
                        mean_uncertainty=mean_unc,
                        band_means=[float(v) for v in band_means[u]],
                        band_profile=[float(v) for v in band_profiles[u]],
                        representative_sample_id=rep_sid,
                        sample_ids=sids,
                    )
                )

        return SomResponse(
            project_id=project.id,
            dataset_id=dataset.id,
            rows=som.rows,
            cols=som.cols,
            epochs=som.epochs,
            total_patches=len(all_sids),
            valid_patches=int(valid_idx.size),
            nodata_patches=int(len(all_sids) - valid_idx.size),
            labeled_patches=sum(1 for sid in label_by_sid if sid in set(all_sids)),
            model_note=model_note,
            active_neurons=active_neurons,
            quantization_error=som.quantization_error,
            topographic_error=som.topographic_error,
            model_iteration=model_iteration,
            bands=dataset.bands,
            classes=project.classes,
            u_matrix=[[float(v) for v in row] for row in som.u_matrix.tolist()],
            hit_grid=[[int(v) for v in row] for row in som.hit_grid.tolist()],
            cells=cells,
        )

    try:
        return await anyio.to_thread.run_sync(_compute)
    except RasterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/som", response_model=SomResponse)
async def get_som(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    dataset_id: int | None = Query(default=None),
    rows: int | None = Query(default=None, ge=2, le=32),
    cols: int | None = Query(default=None, ge=2, le=32),
    epochs: int = Query(default=50, ge=5, le=500),
    patch_size: int | None = Query(default=None, ge=2, le=512),
    stride: int | None = Query(default=None, ge=1, le=512),
) -> SomResponse:
    """Fit and summarize a 2D Self-Organizing Map over dataset patch embeddings."""
    payload = SomRequest(
        dataset_id=dataset_id,
        rows=rows,
        cols=cols,
        epochs=epochs,
        patch_size=patch_size,
        stride=stride,
    )
    return await _run_som(project_id, payload, session, settings)


@router.post("/som", response_model=SomResponse)
async def build_som(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    payload: SomRequest = Body(default_factory=SomRequest),
) -> SomResponse:
    """Fit a custom-configured Self-Organizing Map over dataset patch embeddings."""
    return await _run_som(project_id, payload, session, settings)


async def run_som_classification(
    session: SessionDep,
    settings: SettingsDep,
    project: Project,
    dataset: Dataset,
    payload: SomClassifyRequest,
) -> tuple[Export, Region, UnsupervisedSomResult]:
    """Run unsupervised SOM image classification (no labels required) and export GeoTIFF."""
    region = payload.region or Region(x0=0, y0=0, x1=dataset.width, y1=dataset.height)
    if not (
        0 <= region.x0 < region.x1 <= dataset.width
        and 0 <= region.y0 < region.y1 <= dataset.height
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Region {region.model_dump()} outside dataset bounds {dataset.width}x{dataset.height}",
        )

    m_neurons = payload.rows * payload.cols
    if payload.n_clusters is not None and payload.n_clusters > m_neurons:
        raise HTTPException(
            status_code=422,
            detail=(
                f"n_clusters ({payload.n_clusters}) cannot exceed SOM neuron count "
                f"{payload.rows}x{payload.cols} ({m_neurons})"
            ),
        )

    patch_size = payload.patch_size or settings.patch_size
    stride = payload.stride or settings.resolved_stride()
    export_dir = project_dir(settings, "exports", project.id)
    som_path = export_dir / f"som_ds{dataset.id}_{uuid.uuid4().hex[:8]}.tif"

    def _compute() -> UnsupervisedSomResult:
        arr = load_raster(dataset.path, dataset.nodata, settings.max_raster_elements)
        crop = arr[:, region.y0 : region.y1, region.x0 : region.x1]
        if payload.resolution == "pixel":
            flat = np.moveaxis(crop, 0, -1).reshape(-1, dataset.bands)
            # Same strictness as supervised pixel mode: one missing band makes
            # the pixel nodata instead of being imputed into a cluster.
            valid_mask = np.isfinite(flat).all(axis=1)
            out_shape = (crop.shape[1], crop.shape[2])
            transform = pixel_transform(dataset.transform, region.x0, region.y0)
            grid_meta = None
        else:
            grid = make_grid(crop.shape[1], crop.shape[2], patch_size, stride)
            flat = patch_features(crop, grid)
            valid_mask = patch_validity(crop, grid)
            out_shape = grid.shape
            transform = pixel_transform(dataset.transform, region.x0, region.y0)
            grid_meta = grid_metadata(grid, region.x0, region.y0, stride)
            grid_meta["resolution"] = "patch-cells"

        result = classify_unsupervised_som(
            flat,
            valid_mask,
            out_shape,
            dataset.bands,
            rows=payload.rows,
            cols=payload.cols,
            n_clusters=payload.n_clusters,
            epochs=payload.epochs,
            sigma=payload.sigma,
            learning_rate=payload.learning_rate,
            max_train_samples=payload.max_train_samples,
            random_state=settings.random_state,
        )
        cluster_labels = [c["label"] for c in result.clusters]
        if payload.resolution == "pixel":
            raster = result.cluster_map
        else:
            # Patch cells are painted over their true pixel windows on the source
            # grid, exactly like supervised patch exports.
            from ..services.inference_service import rasterize_cells

            raster = rasterize_cells(
                result.cluster_map,
                valid_mask.reshape(grid.shape),
                grid,
                crop.shape[1],
                crop.shape[2],
            )
        export_som_geotiff(
            som_path,
            raster,
            cluster_labels,
            result.colors,
            dataset.crs,
            transform,
            grid=grid_meta,
            resolution="pixel" if payload.resolution == "pixel" else "patch-cells",
        )
        window = (region.x0, region.y0, region.x1 - region.x0, region.y1 - region.y0)
        validate_export_grid(dataset.path, (som_path,), window)
        return result

    try:
        result = await anyio.to_thread.run_sync(_compute)
    except RasterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    export = Export(
        project_id=project.id,
        dataset_id=dataset.id,
        training_run_id=None,
        type="som",
        path=str(som_path),
        region=region.model_dump(),
    )
    session.add(export)
    await session.commit()
    await session.refresh(export)
    return export, region, result


@router.post("/som/classify", response_model=SomClassifyResponse)
async def classify_som_endpoint(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    payload: SomClassifyRequest = Body(default_factory=SomClassifyRequest),
) -> SomClassifyResponse:
    """Unsupervised Self-Organizing Map image classification (no labels required).

    Clusters pixels (or patches) directly from multi-band spectral values,
    writes a georeferenced colormap GeoTIFF, and returns cluster statistics.
    """
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, payload.dataset_id)
    export, region, result = await run_som_classification(
        session, settings, project, dataset, payload
    )
    return SomClassifyResponse(
        project_id=project.id,
        dataset_id=dataset.id,
        export_id=export.id,
        rows=result.rows,
        cols=result.cols,
        epochs=result.epochs,
        n_clusters=result.n_clusters,
        resolution=payload.resolution,
        region=region,
        shape=list(result.cluster_map.shape),
        total_valid=result.total_valid,
        nodata_count=result.nodata_count,
        quantization_error=result.quantization_error,
        topographic_error=result.topographic_error,
        u_matrix=[[float(v) for v in row] for row in result.u_matrix.tolist()],
        neuron_clusters=[[int(v) for v in row] for row in result.neuron_clusters.tolist()],
        neuron_hits=[[int(v) for v in row] for row in result.neuron_hits.tolist()],
        clusters=[SomClusterSummary(**c) for c in result.clusters],
        cluster_map=result.cluster_map.tolist() if payload.include_map else None,
        exports={
            "som": f"/projects/{project.id}/download/som?dataset_id={dataset.id}",
        },
    )


@router.get("/som/download")
async def download_som_map(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    dataset_id: int | None = Query(default=None),
    export_id: int | None = Query(default=None),
) -> FileResponse:
    """Download an unsupervised SOM classification GeoTIFF (auto-computing if needed)."""
    project = await get_project(session, project_id)

    stmt = select(Export).where(Export.project_id == project_id, Export.type == "som")
    if export_id is not None:
        stmt = stmt.where(Export.id == export_id)
    elif dataset_id is not None:
        stmt = stmt.where(Export.dataset_id == dataset_id)
    stmt = stmt.order_by(Export.id.desc()).limit(1)
    export = (await session.execute(stmt)).scalar_one_or_none()

    if export is None or not Path(export.path).exists():
        dataset = await require_dataset(session, project_id, dataset_id)
        export, _, _ = await run_som_classification(
            session, settings, project, dataset, SomClassifyRequest(dataset_id=dataset.id)
        )

    return FileResponse(
        export.path,
        media_type="image/tiff",
        filename=f"project_{project_id}_som_ds{export.dataset_id}.tif",
    )
