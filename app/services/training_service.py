"""Classical model training (Random Forest / LightGBM), metrics, checkpoints."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split

SUPPORTED_MODELS = ("rf", "lightgbm")
CHECKPOINT_FORMAT = "rsal-checkpoint-v2"
LEGACY_CHECKPOINT_FORMATS = ("rsal-checkpoint-v1",)
CHECKPOINT_REQUIRED_KEYS = (
    "model",
    "model_type",
    "classes",
    "iteration",
    "patch_size",
    "stride",
    "bands",
)
FEATURE_SCHEMA_PIXEL = "pixel-band-vector"
FEATURE_SCHEMA_PATCH = "patch-band-stats"


class TrainingError(ValueError):
    """Not enough data or invalid training configuration."""


class CheckpointError(TrainingError):
    """A checkpoint is unreadable or incompatible with the requested use."""


def build_model(model_type: str, params: dict, random_state: int):
    if model_type == "rf":
        defaults = {"n_estimators": 200, "n_jobs": 2, "random_state": random_state}
        defaults.update(params)
        return RandomForestClassifier(**defaults)
    if model_type == "lightgbm":
        from lightgbm import LGBMClassifier

        defaults = {"n_estimators": 200, "verbosity": -1, "n_jobs": 2, "random_state": random_state}
        defaults.update(params)
        return LGBMClassifier(**defaults)
    raise TrainingError(f"Unsupported model_type '{model_type}'; choose from {SUPPORTED_MODELS}")


def compute_metrics(y_true, y_pred, class_names: list[str]) -> dict:
    labels = list(range(len(class_names)))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    union = matrix.sum(axis=0) + matrix.sum(axis=1) - np.diag(matrix)
    iou = np.divide(np.diag(matrix), union, out=np.zeros(len(labels), dtype=float), where=union != 0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "confusion_matrix": matrix.tolist(),
        "per_class_iou": {name: float(iou[i]) for i, name in enumerate(class_names)},
        "f1_macro": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)),
        "per_class": {
            name: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "iou": float(iou[i]),
                "support": int(support[i]),
            }
            for i, name in enumerate(class_names)
        },
    }


def train_model(
    X: np.ndarray,
    y: list[int],
    class_names: list[str],
    model_type: str,
    params: dict,
    test_size: float,
    random_state: int,
    evaluation_strategy: str = "random",
    groups: np.ndarray | None = None,
) -> tuple[object, dict, str]:
    """Fit a classifier and return (fitted_model, metrics, evaluation_mode).

    Uses a stratified hold-out split when the data supports it; otherwise
    falls back to training-set evaluation (flagged as evaluation="train").
    The returned model is always refit on ALL labeled data.
    """
    y_arr = np.asarray(y)
    present, counts = np.unique(y_arr, return_counts=True)
    if len(present) < 2:
        raise TrainingError(
            f"Training needs labels for at least 2 classes; found {len(present)}. "
            "Submit more labels across classes."
        )
    if len(y_arr) < 4:
        raise TrainingError(f"Training needs at least 4 labeled samples; found {len(y_arr)}.")

    evaluation = "insufficient_train_metrics"
    metrics = None
    if evaluation_strategy not in {"random", "spatial"}:
        raise TrainingError("evaluation_strategy must be 'random' or 'spatial'")
    if evaluation_strategy == "spatial":
        if groups is not None and len(groups) == len(y_arr) and len(np.unique(groups)) >= 3:
            splitter = GroupShuffleSplit(n_splits=20, test_size=test_size, random_state=random_state)
            for train_idx, test_idx in splitter.split(X, y_arr, groups):
                if len(np.unique(y_arr[train_idx])) >= 2 and len(np.unique(y_arr[test_idx])) >= 2:
                    eval_model = build_model(model_type, params, random_state)
                    eval_model.fit(X[train_idx], y_arr[train_idx])
                    metrics = compute_metrics(y_arr[test_idx], eval_model.predict(X[test_idx]), class_names)
                    evaluation = "spatial_holdout"
                    metrics["n_test"] = int(len(test_idx))
                    metrics["held_out_groups"] = int(len(np.unique(groups[test_idx])))
                    break
    elif len(y_arr) >= 8 and counts.min() >= 2:
        try:
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y_arr, test_size=test_size, random_state=random_state, stratify=y_arr
            )
            if len(np.unique(y_te)) >= 2:
                eval_model = build_model(model_type, params, random_state)
                eval_model.fit(X_tr, y_tr)
                metrics = compute_metrics(y_te, eval_model.predict(X_te), class_names)
                evaluation = "random_holdout"
                metrics["n_test"] = int(len(y_te))
        except ValueError:
            pass

    model = build_model(model_type, params, random_state)
    model.fit(X, y_arr)
    if metrics is None:
        # Kept for backward compatibility, but explicitly not a validation score.
        metrics = compute_metrics(y_arr, model.predict(X), class_names)
        group_count = len(np.unique(groups)) if groups is not None else 0
        reason = (
            f"spatial split could not form a two-class independent holdout from {group_count} spatial groups"
            if evaluation_strategy == "spatial"
            else "random stratified holdout lacked sufficient samples or class coverage"
        )
        metrics["evaluation_warning"] = f"Independent evaluation unavailable ({reason}); reported scores are training-set fit metrics."
    metrics["n_train"] = int(len(y_arr))
    metrics["evaluation_strategy"] = evaluation_strategy
    metrics["random_state"] = int(random_state)
    return model, metrics, evaluation


def feature_schema_for(resolution: str) -> str:
    return FEATURE_SCHEMA_PIXEL if resolution == "pixel" else FEATURE_SCHEMA_PATCH


def feature_count(bands: int, feature_schema: str) -> int:
    """Input width the model must expect for a band count and feature family."""
    return bands if feature_schema == FEATURE_SCHEMA_PIXEL else bands * 4


def save_checkpoint(
    path: str | Path,
    model,
    *,
    model_type: str,
    classes: list[str],
    iteration: int,
    patch_size: int,
    stride: int,
    bands: int,
    resolution: str = "patch",
) -> None:
    if resolution not in {"patch", "pixel"}:
        raise TrainingError("resolution must be 'patch' or 'pixel'")
    feature_schema = feature_schema_for(resolution)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        joblib.dump(
            {
                "model": model,
                "model_type": model_type,
                "classes": list(classes),
                "iteration": iteration,
                # The project's patch grid (used by patch-level workflows), not
                # the model's feature window: a pixel checkpoint still records it.
                "patch_size": patch_size,
                "stride": stride,
                "bands": bands,
                "resolution": resolution,
                "feature_schema": feature_schema,
                "n_features": feature_count(bands, feature_schema),
                "format": CHECKPOINT_FORMAT,
            },
            tmp,
        )
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def validate_checkpoint(data) -> dict:
    """Validate a deserialised checkpoint and normalise it for callers.

    Only server-written paths are ever loaded (no upload endpoint accepts a
    serialised model), so this is a compatibility/correctness gate rather than a
    security sandbox: it turns "truncated or foreign file" into an actionable
    409 instead of a ``KeyError``/``AttributeError`` 500 later in inference.
    """
    if not isinstance(data, dict):
        raise CheckpointError(
            "Checkpoint payload is not a RSAL checkpoint (expected a mapping)."
        )
    fmt = data.get("format")
    if fmt not in (CHECKPOINT_FORMAT, *LEGACY_CHECKPOINT_FORMATS):
        raise CheckpointError(
            f"Unsupported checkpoint format {fmt!r}; this build reads "
            f"{CHECKPOINT_FORMAT} and {', '.join(LEGACY_CHECKPOINT_FORMATS)}."
        )
    missing = [key for key in CHECKPOINT_REQUIRED_KEYS if key not in data]
    if missing:
        raise CheckpointError(
            "Checkpoint is missing required field(s) "
            + ", ".join(missing)
            + "; the file is truncated or was written by an incompatible version."
        )

    legacy = fmt in LEGACY_CHECKPOINT_FORMATS
    resolution = data.get("resolution", "patch" if legacy else None)
    if resolution not in {"patch", "pixel"}:
        raise CheckpointError(
            f"Checkpoint resolution {resolution!r} is invalid; expected 'patch' or 'pixel'."
        )
    feature_schema = data.get("feature_schema") or feature_schema_for(resolution)
    if feature_schema not in (FEATURE_SCHEMA_PATCH, FEATURE_SCHEMA_PIXEL):
        raise CheckpointError(
            f"Checkpoint feature schema {feature_schema!r} is invalid; expected "
            f"{FEATURE_SCHEMA_PATCH} or {FEATURE_SCHEMA_PIXEL}."
        )
    expected_resolution = "pixel" if feature_schema == FEATURE_SCHEMA_PIXEL else "patch"
    if resolution != expected_resolution:
        raise CheckpointError(
            f"Checkpoint declares resolution {resolution!r} but feature schema "
            f"{feature_schema!r}; refusing to guess which one is right."
        )

    for key in ("bands", "patch_size", "stride", "iteration"):
        value = data[key]
        if not isinstance(value, (int, np.integer)) or int(value) < 0:
            raise CheckpointError(f"Checkpoint field {key!r} is not a valid integer.")
    if int(data["bands"]) < 1:
        raise CheckpointError("Checkpoint declares zero input bands.")
    if int(data["patch_size"]) < 1 or int(data["stride"]) < 1:
        raise CheckpointError("Checkpoint declares an invalid patch size or stride.")

    classes = data["classes"]
    if not isinstance(classes, list) or not classes or not all(isinstance(c, str) for c in classes):
        raise CheckpointError("Checkpoint class list is missing or malformed.")

    model = data["model"]
    model_classes = getattr(model, "classes_", None)
    if model_classes is None:
        raise CheckpointError("Checkpoint model has no fitted class list (classes_).")
    try:
        resolved = [classes[int(index)] for index in model_classes]
    except (IndexError, TypeError, ValueError) as exc:
        raise CheckpointError(
            "Checkpoint class order does not match the fitted model's classes."
        ) from exc
    if len(resolved) != len(model_classes) or len(set(resolved)) != len(resolved):
        raise CheckpointError(
            "Checkpoint class list is inconsistent with the fitted model's classes."
        )

    n_features = data.get("n_features")
    expected_features = feature_count(int(data["bands"]), feature_schema)
    if n_features is not None and int(n_features) != expected_features:
        raise CheckpointError(
            f"Checkpoint declares {n_features} input features but a {feature_schema} "
            f"over {data['bands']} bands needs {expected_features}."
        )

    normalised = dict(data)
    normalised.update(
        resolution=resolution,
        feature_schema=feature_schema,
        n_features=expected_features,
        legacy=legacy,
        iteration=int(data["iteration"]),
        bands=int(data["bands"]),
        patch_size=int(data["patch_size"]),
        stride=int(data["stride"]),
    )
    return normalised


def load_checkpoint(path: str | Path) -> dict:
    """Load and validate a checkpoint written by :func:`save_checkpoint`."""
    path = Path(path)
    try:
        data = joblib.load(path)
    except TrainingError:
        raise
    except Exception as exc:  # unpickling/IO failure
        raise CheckpointError(
            f"Checkpoint {path.name} could not be read ({type(exc).__name__}); "
            "it is corrupt or was written by an incompatible version."
        ) from exc
    return validate_checkpoint(data)


def align_probabilities(probs: np.ndarray, model_classes: list, all_classes: list[str]) -> np.ndarray:
    """Expand model probabilities to the full project class list (missing classes = 0)."""
    out = np.zeros((len(probs), len(all_classes)), dtype=np.float64)
    index = {c: i for i, c in enumerate(all_classes)}
    for j, c in enumerate(model_classes):
        if c in index:
            out[:, index[c]] = probs[:, j]
    totals = out.sum(axis=1, keepdims=True)
    totals[totals == 0] = 1.0
    return out / totals
