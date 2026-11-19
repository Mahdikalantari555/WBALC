"""Scoring a model on a declared protocol split (Phase 5).

The pipeline that trains a run uses the project's *whole* labelled set: it is a
production model, not an evaluation artifact. Research evaluation therefore does
a second, separate fit on exactly the protocol's training partition and scores it
on the held-out partition. That double work is the price of not leaking: a model
that has already seen the test samples cannot honestly be scored on them.

Everything this module returns is JSON-safe and states its own limits.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
import numpy as np

from ..config import Settings
from ..models import EvaluationResult, Dataset
from .lineage_service import digest, file_identity
from .metrics_service import calibration, coverage_curve, summarize
from .protocol_service import ProtocolError, build_split
from .raster_service import (
    RasterError,
    load_raster,
    make_grid,
    parse_sample_id,
    patch_features,
    patch_validity,
    pixel_features,
)
from .schema_service import SchemaConflict, classification_band_selection
from .training_service import TrainingError, build_model, save_checkpoint


class ResearchError(ValueError):
    """A research operation the engine refuses rather than approximating."""


def _classification_selection(dataset: Dataset) -> dict[str, list]:
    try:
        return classification_band_selection(dataset.band_schema, dataset.bands)
    except SchemaConflict as exc:
        raise ResearchError(str(exc)) from exc


def split_for_project(
    samples: list[dict],
    *,
    protocol: str,
    seed: int,
    test_size: float = 0.3,
    block_size: float = 256.0,
    buffer: float = 0.0,
    spatial_unit: str = "pixels",
) -> dict:
    try:
        return build_split(
            samples,
            protocol=protocol,
            seed=seed,
            test_size=test_size,
            block_size=block_size,
            buffer=buffer,
            spatial_unit=spatial_unit,
        )
    except ProtocolError as exc:
        raise ResearchError(str(exc)) from exc


def _features_for(
    split_entries: list[dict],
    datasets: dict[int, Dataset],
    settings: Settings,
    resolution: str,
    patch_size: int,
    stride: int,
) -> tuple[np.ndarray, list[int], list[dict]]:
    """Extract features for the given samples, in the same order as the input.

    Samples whose pixels are not valid in the raster are dropped from the
    evaluation and reported, never silently scored as an all-zero patch.
    """
    if resolution == "pixel":
        # Point samples: one pixel each, read per dataset in one pass.
        by_dataset: dict[int, list[dict]] = {}
        for entry in split_entries:
            dataset_id = entry.get("dataset_id")
            if dataset_id is None or dataset_id not in datasets:
                continue
            by_dataset.setdefault(int(dataset_id), []).append(entry)
        rows: list[np.ndarray] = []
        kept: list[dict] = []
        for dataset_id, entries in by_dataset.items():
            dataset = datasets[dataset_id]
            selection = _classification_selection(dataset)
            array = load_raster(
                dataset.path,
                dataset.nodata,
                settings.max_raster_elements,
                band_indexes=selection["indices"],
            )
            features, valid = pixel_features(array)
            valid_2d = valid.reshape(dataset.height, dataset.width)
            for entry in entries:
                col = int(np.floor(float(entry["x"])))
                row = int(np.floor(float(entry["y"])))
                if not (0 <= row < dataset.height and 0 <= col < dataset.width):
                    continue
                if not valid_2d[row, col]:
                    continue
                rows.append(features[row * dataset.width + col])
                kept.append(entry)
        if not rows:
            raise ResearchError("no held-out sample falls on valid raster data")
        return np.vstack(rows), [int(entry["class_index"]) for entry in kept], kept

    by_dataset_cells: dict[int, dict[tuple[int, int], dict]] = {}
    for entry in split_entries:
        dataset_id = entry.get("dataset_id")
        if dataset_id is None or dataset_id not in datasets:
            continue
        dataset = datasets[dataset_id]
        grid = make_grid(dataset.height, dataset.width, patch_size, stride)
        col = int(np.floor(float(entry["x"]) / patch_size))
        row = int(np.floor(float(entry["y"]) / patch_size))
        if row < 0 or col < 0 or row >= grid.shape[0] or col >= grid.shape[1]:
            continue
        by_dataset_cells.setdefault(int(dataset_id), {})[(row, col)] = entry

    rows = []
    kept = []
    for dataset_id, cells in by_dataset_cells.items():
        dataset = datasets[dataset_id]
        selection = _classification_selection(dataset)
        array = load_raster(
            dataset.path,
            dataset.nodata,
            settings.max_raster_elements,
            band_indexes=selection["indices"],
        )
        grid = make_grid(dataset.height, dataset.width, patch_size, stride)
        features = patch_features(array, grid)
        valid = patch_validity(array, grid)
        n_cols = grid.shape[1]
        for (row, col), entry in cells.items():
            index = row * n_cols + col
            if not valid[index]:
                continue
            rows.append(features[index])
            kept.append(entry)
    if not rows:
        raise ResearchError("no sample in this partition falls on valid raster data")
    return np.vstack(rows), [int(entry["class_index"]) for entry in kept], kept


def _probability_cube(model, X: np.ndarray, n_classes: int) -> np.ndarray:
    raw = np.asarray(model.predict_proba(X), dtype=np.float64)
    from .training_service import align_probabilities

    model_classes = [int(index) for index in getattr(model, "classes_", range(raw.shape[1]))]
    class_names = [str(index) for index in range(max(n_classes, max(model_classes, default=0) + 1))]
    # align_probabilities is name-based; here we work in integer class indices.
    aligned = np.zeros((raw.shape[0], n_classes), dtype=np.float64)
    for column, class_index in enumerate(model_classes):
        if 0 <= class_index < n_classes:
            aligned[:, class_index] = raw[:, column]
    del class_names
    return aligned


async def score_protocol(
    *,
    project_id: int,
    split: dict,
    datasets: dict[int, Dataset],
    class_names: list[str],
    settings: Settings,
    model_type: str = "rf",
    resolution: str = "patch",
    params: dict | None = None,
    checkpoint_dir: Path | None = None,
) -> dict:
    """Fit on the split's training partition, score on its held-out partition."""
    if split.get("status") != "ok":
        return {
            "status": "insufficient",
            "reason": split.get("reason") or "the split is insufficient",
            "metrics": None,
            "calibration": {"available": False, "reason": "no held-out partition"},
            "coverage": {"available": False, "reason": "no held-out partition"},
            "caveats": list(split.get("caveats") or []),
        }

    # Membership must be resolved back to full sample records (with coordinates).
    train_entries = split.get("train_records") or []
    test_entries = split.get("test_records") or []
    if not train_entries or not test_entries:
        raise ResearchError(
            "the split carries sample ids only; score_protocol needs the resolved records "
            "(pass them from the API layer)"
        )

    patch_size = settings.patch_size
    stride = settings.resolved_stride()
    used_dataset_ids = sorted({
        int(entry["dataset_id"])
        for entry in [*train_entries, *test_entries]
        if entry.get("dataset_id") is not None and int(entry["dataset_id"]) in datasets
    })
    if not used_dataset_ids:
        raise ResearchError("the declared split contains no samples linked to a dataset")
    selections = {dataset_id: _classification_selection(datasets[dataset_id]) for dataset_id in used_dataset_ids}
    if len(used_dataset_ids) > 1 and any(not selection["names"] for selection in selections.values()):
        raise ResearchError(
            "Evaluation samples span multiple datasets, but at least one dataset has no "
            "declared predictor-band names. Their ordered feature schemas cannot be proven compatible."
        )
    signatures = {
        tuple(name.casefold() for name in selection["names"])
        if selection["names"]
        else (None, len(selection["indices"]))
        for selection in selections.values()
    }
    if len(signatures) > 1:
        raise ResearchError(
            "Evaluation samples use incompatible classification predictor bands; "
            "the train and test partitions must share one ordered predictor schema."
        )
    feature_selection = selections[used_dataset_ids[0]]

    def _fit_and_score():
        X_train, y_train, kept_train = _features_for(
            train_entries, datasets, settings, resolution, patch_size, stride
        )
        X_test, y_test, kept_test = _features_for(
            test_entries, datasets, settings, resolution, patch_size, stride
        )
        if len(set(y_train)) < 2:
            raise ResearchError(
                "the training partition contains fewer than two classes after dropping "
                "invalid samples"
            )
        model = build_model(model_type, params or {}, int(split["configuration"]["seed"]))
        model.fit(X_train, y_train)
        probabilities = _probability_cube(model, X_test, len(class_names))
        predicted = probabilities.argmax(axis=1)
        return model, kept_train, kept_test, y_test, predicted, probabilities

    try:
        model, kept_train, kept_test, y_test, predicted, probabilities = (
            await anyio.to_thread.run_sync(_fit_and_score)
        )
    except (RasterError, TrainingError) as exc:
        raise ResearchError(str(exc)) from exc

    metrics = summarize(y_test, predicted, class_names)
    metrics["feature_selection"] = {
        "predictor_band_names": feature_selection["names"],
        "excluded_band_names": feature_selection["excluded_names"],
        "by_dataset": {
            str(dataset_id): {
                "predictor_band_indices": selection["indices"],
                "predictor_band_names": selection["names"],
                "excluded_band_indices": selection["excluded_indices"],
                "excluded_band_names": selection["excluded_names"],
            }
            for dataset_id, selection in selections.items()
        },
    }
    metrics["evaluation"] = f"{split['protocol']}_holdout"
    metrics["n_train"] = len(kept_train)
    metrics["n_test"] = len(kept_test)
    metrics["dropped"] = {
        "train": len(train_entries) - len(kept_train),
        "test": len(test_entries) - len(kept_test),
        "reason": "sample fell outside the raster or on invalid (nodata) pixels",
    }

    # Persist a checkpoint of the evaluation model so the score is reproducible from
    # bytes, not just from a config dict.
    checkpoint_dataset = datasets[int(kept_train[0]["dataset_id"])]
    checkpoint_selection = selections[checkpoint_dataset.id]
    artifact = None
    if checkpoint_dir is not None:
        path = checkpoint_dir / f"eval_{uuid.uuid4().hex[:10]}_{model_type}.joblib"
        await anyio.to_thread.run_sync(
            lambda: save_checkpoint(
                path,
                model,
                model_type=model_type,
                classes=list(class_names),
                iteration=0,
                patch_size=patch_size,
                stride=stride,
                bands=int(checkpoint_dataset.bands),
                resolution=resolution,
                band_schema=checkpoint_dataset.band_schema,
                taxonomy=None,
                predictor_band_indices=checkpoint_selection["indices"],
            )
        )
        identity = await anyio.to_thread.run_sync(lambda: file_identity(path))
        artifact = {"path": str(path), "name": path.name, **(identity or {})}

    return {
        "status": "ok",
        "metrics": metrics,
        "calibration": await anyio.to_thread.run_sync(
            lambda: calibration(y_test, probabilities, class_names)
        ),
        "coverage": await anyio.to_thread.run_sync(
            lambda: coverage_curve(y_test, probabilities)
        ),
        "artifact": artifact,
        "caveats": list(split.get("caveats") or [])
        + [
            "The evaluation model was refit on the training partition only; the project's "
            "production run is a different fit and can legitimately differ.",
            "Samples that fall outside the raster or on nodata pixels are excluded and counted "
            "in `metrics.dropped`.",
        ],
    }


def build_result(
    *,
    project_id: int,
    protocol_id: int,
    split: dict,
    scored: dict,
    model_type: str,
    resolution: str,
    params: dict,
) -> EvaluationResult:
    config = {
        "model_type": model_type,
        "resolution": resolution,
        "params": params,
        "seed": split.get("configuration", {}).get("seed"),
        "protocol": split.get("protocol"),
    }
    status = scored.get("status", "ok")
    caveats = list(scored.get("caveats") or [])
    if status != "ok":
        caveats.append(f"insufficient: {scored.get('reason')}")
    return EvaluationResult(
        project_id=project_id,
        protocol_id=protocol_id,
        protocol_split_hash=split.get("split_hash"),
        model_type=model_type,
        resolution=resolution,
        config=config,
        metrics=scored.get("metrics") or {},
        calibration=scored.get("calibration") or {},
        coverage=scored.get("coverage") or {},
        status=status,
        caveats=caveats,
    )


def research_disclaimer() -> dict:
    """The standing scientific-validity statement, included in every report."""
    return {
        "software_validation": "verified by automated tests on synthetic data",
        "scientific_validity": "not established",
        "detail": (
            "Passing software tests shows the calculations behave as specified on synthetic "
            "fixtures. It does not show that a water map is correct on real imagery. That "
            "requires operator-supplied independent reference data, which this engine does "
            "not bundle and cannot fetch."
        ),
    }


def bundle_digest(bundle: dict) -> str:
    return digest(bundle)
