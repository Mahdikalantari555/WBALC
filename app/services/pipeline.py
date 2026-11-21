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
    check_element_budget,
    load_raster,
    make_grid,
    parse_sample_id,
    patch_features,
    patch_validity,
    pixel_features,
)
from .lineage_service import build_run_manifest, file_identity
from .label_service import latest_labels
from .schema_service import (
    SchemaConflict,
    classification_band_selection,
    compare_schemas,
)
from .taxonomy_service import binary_plan, taxonomy_snapshot
from .training_service import TrainingError, save_checkpoint, train_model


async def run_training(
    session: AsyncSession,
    settings: Settings,
    project: Project,
    *,
    model_type: str = "rf",
    resolution: str = "patch",
    test_size: float | None = None,
    params: dict | None = None,
    evaluation_strategy: str = "random",
    accept_unverified_schema: bool = False,
) -> TrainingRun:
    """Train on the current labeled data and persist checkpoint + metrics.

    `iteration` is always derived here (one greater than the project's current
    maximum; the labels' own iterations when no run exists yet), never taken
    from a client: a repeated client value must not create duplicate iterations.
    """
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

    # Class semantics are snapshotted with the run: later project edits must not
    # retroactively change what this model's classes meant.
    if project.taxonomy:
        binary_interpretation = project.taxonomy.get("binary_interpretation", "water_vs_non_water")
        taxonomy = taxonomy_snapshot(project.taxonomy, binary_interpretation=binary_interpretation)
    else:
        # A generic/legacy project: record its class order, but do not claim water
        # semantics it never opted into (no derived binary product).
        binary_interpretation = None
        taxonomy = {
            "version": None,
            "classes": list(project.classes),
            "source": "legacy",
            "binary_interpretation": None,
        }

    # All contributing rasters must describe the same ordered bands. Band counts
    # that merely happen to match are not proof of semantic compatibility.
    band_schema = _verify_training_schemas(
        {ds_id: datasets[ds_id] for ds_id in sorted(by_dataset)},
        accept_unverified_schema,
    )
    source_bands = datasets[min(by_dataset)].bands
    feature_selection = classification_band_selection(band_schema, source_bands)
    predictor_band_indices = feature_selection["indices"]

    def _extract() -> tuple[np.ndarray, list[int], int, np.ndarray]:
        X_parts: list[np.ndarray] = []
        y_out: list[int] = []
        group_out: list[str] = []
        bands = source_bands
        for ds_id, items in by_dataset.items():
            ds = datasets[ds_id]
            if resolution == "pixel":
                # Read only 256x256 blocks that contain labels; avoid materializing
                # the complete input cube just to extract sparse training pixels.
                by_block: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
                for (row, col), target in items.items():
                    by_block.setdefault((row // 256, col // 256), []).append((row, col, target))
                with rasterio.open(ds.path) as src:
                    # Checked before any block is read, so the refusal is cheap.
                    check_element_budget(
                        len(predictor_band_indices),
                        src.height,
                        src.width,
                        settings.max_raster_elements,
                        what="pixel training extraction",
                    )
                    bands = src.count
                    for (block_y, block_x), samples in by_block.items():
                        row0, col0 = block_y * 256, block_x * 256
                        row1, col1 = min(src.height, row0 + 256), min(src.width, col0 + 256)
                        window = Window(col0, row0, col1 - col0, row1 - row0)
                        block = src.read(
                            indexes=[index + 1 for index in predictor_band_indices],
                            window=window,
                            masked=True,
                            out_dtype="float32",
                        ).filled(np.nan)
                        features, valid = pixel_features(block)
                        block_width = col1 - col0
                        for row, col, target in samples:
                            local = (row - row0) * block_width + (col - col0)
                            if valid[local]:
                                X_parts.append(features[local])
                                y_out.append(target)
                                group_out.append(f"{ds_id}:{block_y}:{block_x}")
            else:
                arr = load_raster(
                    ds.path,
                    ds.nodata,
                    settings.max_raster_elements,
                    band_indexes=predictor_band_indices,
                )
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

    # Iteration identity is server-owned: one greater than the project's current
    # maximum run. When no run exists yet, fall back to the labels' iterations
    # (a cold start that resumes an imported labeling history).
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
            band_schema=band_schema,
            taxonomy=taxonomy,
            predictor_band_indices=predictor_band_indices,
        )
    )

    # Lineage: which exact bytes, which label *versions*, which config, which code.
    # Built after the checkpoint is written so its hash is part of the record.
    checkpoint_identity = await anyio.to_thread.run_sync(lambda: file_identity(checkpoint))
    manifest = build_run_manifest(
        project=project,
        run_config={
            "model_type": model_type,
            "resolution": resolution,
            "evaluation_strategy": evaluation_strategy,
            "random_state": settings.random_state,
            "test_size": test_size if test_size is not None else settings.test_size,
            "params": params or {},
            "hybrid": {k: v for k, v in (params or {}).items()},
            "bands": bands,
            "predictor_band_indices": predictor_band_indices,
            "predictor_band_names": feature_selection["names"],
            "excluded_band_indices": feature_selection["excluded_indices"],
            "excluded_band_names": feature_selection["excluded_names"],
            "iteration": iteration,
            "patch_size": patch_size,
            "stride": stride,
            "checkpoint_sha256": (checkpoint_identity or {}).get("sha256"),
        },
        datasets=[datasets[ds_id] for ds_id in sorted(by_dataset)],
        labels=latest_labels(labels),
        taxonomy=taxonomy,
        band_schema=band_schema,
        storage_dir=settings.storage_dir,
    )

    run = TrainingRun(
        project_id=project.id,
        iteration=iteration,
        model_type=model_type,
        checkpoint_path=str(checkpoint),
        classes=project.classes,
        # The classes this model actually learned, in project order. `run.classes`
        # stays the full project list so pre-existing consumers keep working; a
        # derived product must consult `trained_classes`, because a class the model
        # never saw has no probabilities to recode.
        trained_classes=[project.classes[i] for i in sorted(set(y_final))],
        n_samples=len(y_final),
        metrics=metrics,
        manifest=manifest,
        checkpoint_sha256=(checkpoint_identity or {}).get("sha256"),
        params={
            **(params or {}),
            "resolution": resolution,
            "evaluation_strategy": evaluation_strategy,
            "random_state": settings.random_state,
            "test_size": test_size if test_size is not None else settings.test_size,
            "bands": bands,
            "predictor_band_indices": predictor_band_indices,
            "predictor_band_names": feature_selection["names"],
            "excluded_band_indices": feature_selection["excluded_indices"],
            "excluded_band_names": feature_selection["excluded_names"],
            "feature_config": "per-pixel predictor-band values" if resolution == "pixel" else "per-predictor-band mean/std/min/max patch summary",
            "dataset_ids": sorted(by_dataset),
            "band_schema": band_schema,
            "band_schema_verified": bool(band_schema.get("declared")),
            "schema_override": bool(band_schema.get("override")),
            "taxonomy": taxonomy,
            "binary": (
                binary_plan(list(project.classes), binary_interpretation)
                if binary_interpretation
                else None
            ),
        },
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


def _verify_training_schemas(datasets: dict[int, Dataset], accept_unverified: bool) -> dict:
    """Require every contributing raster to share one declared band schema.

    Returns the schema to record in the checkpoint. When identity cannot be
    proven, training is refused unless the caller explicitly accepts an
    undeclared schema — and that fact is recorded, not glossed over.
    """
    from .schema_service import SchemaConflict

    schemas = {ds_id: (ds.band_schema or None) for ds_id, ds in datasets.items()}
    counts = {ds_id: ds.bands for ds_id, ds in datasets.items()}
    if len(set(counts.values())) > 1:
        detail = ", ".join(f"dataset {ds_id}: {count} bands" for ds_id, count in counts.items())
        raise SchemaConflict(f"Contributing rasters have different band counts ({detail})")

    declared = {ds_id: schema for ds_id, schema in schemas.items() if schema and schema.get("declared")}
    if declared:
        digests = {schema.get("digest") for schema in declared.values()}
        if len(digests) > 1 or len(declared) != len(schemas):
            if not accept_unverified:
                raise SchemaConflict(
                    "Contributing rasters do not all declare the same ordered band schema "
                    f"({len(declared)} of {len(schemas)} datasets declare one); refuse to "
                    "concatenate them by band count alone. Re-upload with explicit band "
                    "names, or retrain with accept_unverified_schema=true to record an override."
                )
            base = next(iter(declared.values()))
            return {**base, "override": True, "override_reason": "mixed or undeclared schemas accepted by the caller"}
        return {**next(iter(declared.values())), "override": False}

    if not accept_unverified:
        raise SchemaConflict(
            "None of the contributing rasters declares band names, so the model's input "
            "identity would be unverifiable. Re-upload with band_names (and optionally "
            "sensor), or retrain with accept_unverified_schema=true to record an override."
        )
    first = next(iter(schemas.values())) or {}
    return {
        **(first or {}),
        "declared": False,
        "override": True,
        "override_reason": "caller accepted an undeclared band schema",
    }


def resolve_inference_contract(
    run: TrainingRun,
    checkpoint: dict,
    dataset: Dataset,
    accept_unverified: bool,
) -> dict:
    """Verify that a raster's declared bands match the model's, fail closed.

    Returns provenance for the response/export. Raises 409 when the identity
    cannot be proven and the caller did not explicitly accept an unverified
    schema; a band-count match alone is never enough.
    """
    if checkpoint["bands"] != dataset.bands:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Model expects {checkpoint['bands']} bands but dataset "
                f"'{dataset.filename}' has {dataset.bands}"
            ),
        )
    expected = checkpoint.get("band_schema") or (run.params or {}).get("band_schema")
    actual = dataset.band_schema
    verified, reason = compare_schemas(
        expected,
        actual,
        expected_band_count=checkpoint["bands"],
        actual_band_count=dataset.bands,
    )
    feature_record = {
        "predictor_band_indices": checkpoint.get("predictor_band_indices", list(range(checkpoint["bands"]))),
        "predictor_band_names": checkpoint.get("predictor_band_names") or [],
        "excluded_band_indices": checkpoint.get("excluded_band_indices") or [],
        "excluded_band_names": checkpoint.get("excluded_band_names") or [],
    }
    if verified:
        return {"verified": True, "reason": reason, "override": False, **feature_record}
    if not accept_unverified:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot prove the selected raster carries the same ordered bands as the "
                f"model: {reason}. Upload a raster with declared band names, or repeat the "
                f"request with accept_unverified_schema=true to record an explicit override."
            ),
        )
    return {
        "verified": False,
        "reason": f"{reason} (overridden by the caller)",
        "override": True,
        **feature_record,
    }


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
    if checkpoint.get("legacy_scl_predictor"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Training run {run.iteration} was trained with SCL as a model input. "
                "SCL is QA data and cannot be used for classification; retrain the project "
                "with the current feature selection before inference."
            ),
        )
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
