"""Research metrics with honest undefined states (Phase 5).

Scikit-learn's `zero_division=0` turns "this class was never predicted and never
present" into a 1.0 precision/recall for some aggregates and 0.0 for others,
depending on the version and the average. Both are fabrications. This module
computes the same quantities and reports **null with a reason** whenever the
denominator is zero, so a report can never imply validation of a class that had
no support.

Everything here is pure: arrays in, JSON-safe dicts out.
"""

from __future__ import annotations

import math

import numpy as np

# Metric identity: what an "undefined" value means, per metric.
UNDEFINED_REASONS = {
    "precision": "no sample was predicted as this class",
    "recall": "this class has no held-out reference samples",
    "f1": "precision or recall is undefined for this class",
    "iou": "this class appears in neither the reference nor the prediction",
    "specificity": "there are no true negatives to measure against",
}


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def confusion(y_true, y_pred, n_classes: int) -> np.ndarray:
    """Rows = reference (truth), columns = prediction."""
    matrix = np.zeros((n_classes, n_classes), dtype=np.int64)
    for truth, predicted in zip(np.asarray(y_true), np.asarray(y_pred)):
        t, p = int(truth), int(predicted)
        if 0 <= t < n_classes and 0 <= p < n_classes:
            matrix[t, p] += 1
    return matrix


def per_class_metrics(y_true, y_pred, class_names: list[str]) -> dict:
    """Per-class precision/recall/F1/IoU/specificity/support, nulls preserved."""
    n = len(class_names)
    matrix = confusion(y_true, y_pred, n)
    total = int(matrix.sum())
    rows = []
    for index, name in enumerate(class_names):
        tp = int(matrix[index, index])
        reference = int(matrix[index, :].sum())
        predicted = int(matrix[:, index].sum())
        tn = total - reference - predicted + tp
        precision = _safe_ratio(tp, predicted)
        recall = _safe_ratio(tp, reference)
        f1 = (
            None
            if precision is None or recall is None or precision + recall == 0
            else 2 * precision * recall / (precision + recall)
        )
        union = reference + predicted - tp
        rows.append(
            {
                "class_name": name,
                "class_index": index,
                "support": reference,
                "predicted": predicted,
                "true_positives": tp,
                "false_negatives": reference - tp,
                "false_positives": predicted - tp,
                "true_negatives": tn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "iou": _safe_ratio(tp, union),
                "specificity": _safe_ratio(tn, tn + (predicted - tp)),
                "undefined": {
                    metric: reason
                    for metric, reason in UNDEFINED_REASONS.items()
                    if {
                        "precision": precision,
                        "recall": recall,
                        "f1": f1,
                        "iou": _safe_ratio(tp, union),
                        "specificity": _safe_ratio(tn, tn + (predicted - tp)),
                    }[metric]
                    is None
                },
            }
        )
    return {"classes": list(class_names), "class_count": n, "n_samples": total, "per_class": rows, "matrix": matrix.tolist()}


def macro_average(per_class: list[dict], metric: str, *, only_defined: bool = False) -> dict:
    """Macro average plus how much of the class list actually contributed.

    `only_defined=False` reports the average over classes with a defined value and
    states how many were skipped — an average that silently drops classes makes a
    model look better than the evidence supports, and an average that treats an
    undefined metric as 1.0 or 0.0 is simply wrong.
    """
    values = [row[metric] for row in per_class if row[metric] is not None]
    skipped = [row["class_name"] for row in per_class if row[metric] is None]
    if not values:
        return {"value": None, "classes_used": 0, "classes_skipped": skipped, "reason": "no class has a defined value for this metric"}
    return {
        "value": float(sum(values) / len(values)),
        "classes_used": len(values),
        "classes_skipped": skipped,
        "reason": None if not skipped else "classes without a defined value are excluded, not imputed",
    }


def balanced_accuracy(y_true, y_pred, class_names: list[str]) -> dict:
    """Mean per-class recall over classes present in the reference.

    A class with no reference samples contributes nothing (it cannot be recalled);
    the count of contributing classes is reported so a two-class average is never
    mistaken for a five-class one.
    """
    n = len(class_names)
    matrix = confusion(y_true, y_pred, n)
    recalls = []
    contributing = []
    missing = []
    for index, name in enumerate(class_names):
        reference = int(matrix[index, :].sum())
        if reference == 0:
            missing.append(name)
            continue
        recalls.append(int(matrix[index, index]) / reference)
        contributing.append(name)
    if not recalls:
        return {"value": None, "classes_used": [], "classes_missing": missing, "reason": "no class has held-out reference samples"}
    return {
        "value": float(sum(recalls) / len(recalls)),
        "classes_used": contributing,
        "classes_missing": missing,
        "reason": None,
    }


def summarize(y_true, y_pred, class_names: list[str]) -> dict:
    """The full research metric block stored on an evaluation record."""
    block = per_class_metrics(y_true, y_pred, class_names)
    matrix = np.array(block["matrix"], dtype=np.int64)
    total = int(matrix.sum())
    correct = int(np.trace(matrix))
    block["accuracy"] = _safe_ratio(correct, total)
    block["balanced_accuracy"] = balanced_accuracy(y_true, y_pred, class_names)
    block["macro"] = {
        "precision": macro_average(block["per_class"], "precision"),
        "recall": macro_average(block["per_class"], "recall"),
        "f1": macro_average(block["per_class"], "f1"),
        "iou": macro_average(block["per_class"], "iou"),
    }
    weights = np.array([row["support"] for row in block["per_class"]], dtype=np.float64)
    weighted = {}
    for metric in ("precision", "recall", "f1"):
        values = np.array(
            [row[metric] if row[metric] is not None else 0.0 for row in block["per_class"]],
            dtype=np.float64,
        )
        weighted[metric] = (
            float(np.average(values, weights=weights)) if weights.sum() > 0 else None
        )
    block["weighted"] = {
        **weighted,
        "note": "classes without a defined value are imputed as 0 here, because a weighted "
        "mean needs every supporting class; use `macro` for the imputation-free view",
    }
    block["insufficient"] = total == 0
    block["reason"] = "no held-out samples" if total == 0 else None
    return block


# ------------------------------------------------------- calibration / coverage
def calibration(y_true, probabilities: np.ndarray, class_names: list[str], *, bins: int = 10) -> dict:
    """Expected/maximum calibration error and Brier score on held-out samples.

    Only *defined* here because the caller supplied held-out labels and
    probabilities together; the sample count is part of the result so a
    one-sample "calibration" cannot be quoted as evidence.
    """
    probabilities = np.asarray(probabilities, dtype=np.float64)
    y_true = np.asarray(y_true)
    n = len(y_true)
    if n == 0:
        return {"available": False, "reason": "no held-out samples", "n_samples": 0}
    confidence = probabilities.max(axis=1)
    predicted = probabilities.argmax(axis=1)
    correct = (predicted == y_true).astype(np.float64)

    edges = np.linspace(0.0, 1.0, bins + 1)
    rows = []
    ece = 0.0
    mce = 0.0
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        mask = (confidence > low if index else confidence >= low) & (confidence <= high)
        count = int(mask.sum())
        if count == 0:
            continue
        mean_confidence = float(confidence[mask].mean())
        accuracy = float(correct[mask].mean())
        gap = abs(accuracy - mean_confidence)
        ece += gap * count / n
        mce = max(mce, gap)
        rows.append(
            {
                "bin": index,
                "lower": float(low),
                "upper": float(high),
                "count": count,
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "gap": gap,
            }
        )

    one_hot = np.zeros_like(probabilities)
    valid_rows = (y_true >= 0) & (y_true < probabilities.shape[1])
    one_hot[np.arange(n)[valid_rows], y_true[valid_rows]] = 1.0
    brier = float(((probabilities - one_hot) ** 2).sum(axis=1).mean())
    return {
        "available": True,
        "n_samples": n,
        "bins": bins,
        "expected_calibration_error": float(ece),
        "maximum_calibration_error": float(mce),
        "brier_score": brier,
        "mean_confidence": float(confidence.mean()),
        "accuracy": float(correct.mean()),
        "per_bin": rows,
        "method": "equal-width confidence bins over the predicted class; multiclass Brier sum",
        "caveat": (
            "Calibration measured on the held-out split only. With few held-out samples these "
            "numbers are noisy: read them with the sample count."
        ),
    }


def coverage_curve(
    y_true, probabilities: np.ndarray, thresholds: list[float] | None = None
) -> dict:
    """Accuracy retained at successive abstention thresholds.

    A model that is 95% accurate on the 40% of pixels it is confident about has not
    earned that accuracy on the other 60%; the curve makes the trade explicit.
    """
    probabilities = np.asarray(probabilities, dtype=np.float64)
    y_true = np.asarray(y_true)
    n = len(y_true)
    if n == 0:
        return {"available": False, "reason": "no held-out samples", "n_samples": 0}
    confidence = probabilities.max(axis=1)
    predicted = probabilities.argmax(axis=1)
    correct = predicted == y_true
    thresholds = thresholds or [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    rows = []
    for threshold in thresholds:
        keep = confidence >= threshold
        retained = int(keep.sum())
        rows.append(
            {
                "threshold": float(threshold),
                "retained": retained,
                "coverage": retained / n,
                "accuracy": float(correct[keep].mean()) if retained else None,
            }
        )
    return {
        "available": True,
        "n_samples": n,
        "points": rows,
        "method": "max predicted probability as the confidence score",
        "caveat": "Coverage/accuracy trade-off on held-out samples; not a validation of the abstention rule itself.",
    }


# ------------------------------------------------------------- area accuracy
def area_error(
    mapped_m2: float,
    reference_m2: float,
    *,
    reference_source: str,
    reference_method: str,
) -> dict:
    """Signed/absolute area error against an *independent* reference.

    Refusing to invent a reference is the point: a mapped area is never compared
    with itself, and the reference's provenance is mandatory.
    """
    if reference_m2 < 0 or mapped_m2 < 0:
        raise ValueError("areas must not be negative")
    signed = mapped_m2 - reference_m2
    absolute = abs(signed)
    return {
        "mapped_area_m2": float(mapped_m2),
        "reference_area_m2": float(reference_m2),
        "signed_error_m2": float(signed),
        "absolute_error_m2": float(absolute),
        "relative_error": (float(signed) / reference_m2) if reference_m2 else None,
        "absolute_error_ha": float(absolute) / 10_000.0,
        "units": "m2",
        "reference_source": reference_source,
        "reference_method": reference_method,
        "caveat": "Error is only as good as the independent reference; the engine does not validate it.",
    }


def scene_distribution(values: list[float], regions: list[str]) -> dict:
    """Scene-level distribution instead of a pixel pool.

    Pooling millions of pixels from three scenes and quoting one standard error
    treats correlated pixels as independent replicates. This reports the
    per-scene values, their spread, and says plainly that n is the number of
    scenes.
    """
    finite = [float(value) for value in values if value is not None and math.isfinite(value)]
    if not finite:
        return {"available": False, "reason": "no scene has a finite value", "n_units": 0}
    array = np.asarray(finite, dtype=np.float64)
    return {
        "available": True,
        "resampling_unit": "scene",
        "n_units": len(finite),
        "regions": list(regions),
        "values": finite,
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "std": float(array.std(ddof=1)) if len(array) > 1 else None,
        "min": float(array.min()),
        "max": float(array.max()),
        "caveat": (
            "n is the number of independent scenes, not pixels. Per-pixel pooling would "
            "inflate significance by treating correlated pixels as replicates."
        ),
    }
