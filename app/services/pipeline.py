"""End-to-end training pipeline shared by /train and label auto-training."""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
import numpy as np
import rasterio
from rasterio.windows import Window
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import Dataset, Project, TrainingRun
from ..storage import project_dir
from .label_service import build_pixel_training_targets, build_training_targets
from .raster_service import (
    RasterError,
    load_raster,
    make_grid,
    parse_sample_id,
    patch_features,
    patch_validity,
    pixel_features,
)
from .training_service import TrainingError, save_checkpoint, train_model


async def run_training(
    session: AsyncSession,
    settings: Settings,
    project: Project,
    *,
    model_type: str = "rf",
    resolution: str = "patch",
    iteration: int | None = None,
    test_size: float | None = None,
    params: dict | None = None,
    evaluation_strategy: str = "random",
) -> TrainingRun:
    """Train on the current labeled data and persist checkpoint + metrics."""
    from ..api.deps import project_labels

    labels = await project_labels(session, project.id)
    result = await session.execute(select(Dataset).where(Dataset.project_id == project.id))
    datasets = {d.id: d for d in result.scalars()}
    if not datasets:
        raise TrainingError("Project has no dataset; upload a GeoTIFF first")
    default_dataset = max(datasets.values(), key=lambda d: d.id)

    patch_size = settings.patch_size
    stride = settings.resolved_stride()
    grids = {
        ds_id: make_grid(ds.height, ds.width, patch_size, stride)
        for ds_id, ds in datasets.items()
    }

    if resolution not in {"patch", "pixel"}:
        raise TrainingError("resolution must be 'patch' or 'pixel'")
    if resolution == "pixel":
        pixel_targets = build_pixel_training_targets(labels, datasets, default_dataset, project.classes)
        if not pixel_targets:
            raise TrainingError("No usable labeled pixels; labels must fall within a dataset")
        by_dataset = pixel_targets
    else:
        sids, y, _ = build_training_targets(labels, datasets, default_dataset, grids, project.classes)
        if not sids:
            raise TrainingError("No usable labeled patches. Submit labels whose geometry falls inside a dataset.")
        by_dataset: dict[int, list[tuple[int, int, int]]] = {}
        for sid, target in zip(sids, y):
            parsed = parse_sample_id(sid)
            if parsed is not None and parsed[0] in datasets:
                by_dataset.setdefault(parsed[0], []).append((parsed[1], parsed[2], target))

    def _extract() -> tuple[np.ndarray, list[int], int, np.ndarray]:
        X_parts: list[np.ndarray] = []
        y_out: list[int] = []
        group_out: list[str] = []
        bands = 0
        for ds_id, items in by_dataset.items():
            ds = datasets[ds_id]
            if resolution == "pixel":
                # Read only 256x256 blocks that contain labels; avoid materializing
                # the complete input cube just to extract sparse training pixels.
                by_block: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
                for (row, col), target in items.items():
                    by_block.setdefault((row // 256, col // 256), []).append((row, col, target))
                with rasterio.open(ds.path) as src:
                    if src.count * src.width * src.height > settings.max_raster_elements:
                        raise RasterError(f"Raster exceeds configured processing limit ({src.count}x{src.height}x{src.width})")
                    bands = src.count
                    for (block_y, block_x), samples in by_block.items():
                        row0, col0 = block_y * 256, block_x * 256
                        row1, col1 = min(src.height, row0 + 256), min(src.width, col0 + 256)
                        window = Window(col0, row0, col1 - col0, row1 - row0)
                        block = src.read(window=window, masked=True, out_dtype="float32").filled(np.nan)
                        features, valid = pixel_features(block)
                        block_width = col1 - col0
                        for row, col, target in samples:
                            local = (row - row0) * block_width + (col - col0)
                            if valid[local]:
                                X_parts.append(features[local])
                                y_out.append(target)
                                group_out.append(f"{ds_id}:{block_y}:{block_x}")
            else:
                arr = load_raster(ds.path, ds.nodata, settings.max_raster_elements)
                bands = arr.shape[0]
                grid = grids[ds_id]
                feats = patch_features(arr, grid)
                patch_valid = patch_validity(arr, grid)
                n_cols = len(grid.xs)
                for row, col, target in items:
                    index = row * n_cols + col
                    if 0 <= row < len(grid.ys) and 0 <= col < n_cols and patch_valid[index]:
                        X_parts.append(feats[index])
                        y_out.append(target)
                        py, px = grid.ys[row], grid.xs[col]
                        group_out.append(f"{ds_id}:{py // 256}:{px // 256}")
        if not X_parts:
            raise TrainingError("No labeled sample intersects valid raster data")
        return np.vstack(X_parts), y_out, bands, np.asarray(group_out, dtype=str)

    try:
        X, y_final, bands, spatial_groups = await anyio.to_thread.run_sync(_extract)
    except RasterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if iteration is None:
        runs = await session.execute(
            select(TrainingRun.iteration)
            .where(TrainingRun.project_id == project.id)
            .order_by(TrainingRun.iteration.desc())
            .limit(1)
        )
        last = runs.scalar_one_or_none()
        if last is not None:
            iteration = last + 1
        else:
            iteration = max((l.iteration for l in labels), default=0)

    def _train():
        return train_model(
            X,
            y_final,
            project.classes,
            model_type,
            params or {},
            test_size if test_size is not None else settings.test_size,
            settings.random_state,
            evaluation_strategy=evaluation_strategy,
            groups=spatial_groups,
        )

    model, metrics, evaluation = await anyio.to_thread.run_sync(_train)
    metrics["evaluation"] = evaluation

    models_dir = project_dir(settings, "models", project.id)
    checkpoint = models_dir / f"model_iter_{iteration}_{model_type}_{uuid.uuid4().hex[:8]}.joblib"
    await anyio.to_thread.run_sync(
        lambda: save_checkpoint(
            checkpoint,
            model,
            model_type=model_type,
            classes=project.classes,
            iteration=iteration,
            patch_size=patch_size,
            stride=stride,
            bands=bands,
            resolution=resolution,
        )
    )

    run = TrainingRun(
        project_id=project.id,
        iteration=iteration,
        model_type=model_type,
        checkpoint_path=str(checkpoint),
        classes=project.classes,
        n_samples=len(y_final),
        metrics=metrics,
        params={
            **(params or {}),
            "resolution": resolution,
            "evaluation_strategy": evaluation_strategy,
            "random_state": settings.random_state,
            "test_size": test_size if test_size is not None else settings.test_size,
            "bands": bands,
            "feature_config": "per-pixel band values" if resolution == "pixel" else "per-band mean/std/min/max patch summary",
            "dataset_ids": sorted(by_dataset),
        },
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


def training_error_to_http(exc: TrainingError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def checkpoint_or_409(run: TrainingRun) -> dict:
    from .training_service import CheckpointError, load_checkpoint

    path = Path(run.checkpoint_path)
    if not path.exists():
        raise HTTPException(status_code=409, detail=f"Checkpoint missing on disk: {path.name}")
    try:
        checkpoint = load_checkpoint(path)
    except CheckpointError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Training run {run.iteration} has an unusable checkpoint: {exc} Retrain the project.",
        ) from exc
    if checkpoint.get("classes") != list(run.classes):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Checkpoint class order for iteration {run.iteration} does not match the "
                "run's recorded classes; refusing to label predictions with the wrong "
                "class names. Retrain the project."
            ),
        )
    return checkpoint
