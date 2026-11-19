"""Research report bundles: JSON, CSV and Markdown from immutable records (Phase 5).

A report is a *view* of stored records, never a source of new claims:

- every included run/protocol/result is named by id and hash,
- anything that could not be established (no independent area reference, an
  insufficient split, a legacy run without a manifest) is listed under
  `caveats`/`limitations` rather than omitted,
- the bundle is regenerable: run the same request against the same database and
  the canonical digest is identical (no timestamps inside the hashed payload).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .lineage_service import digest

BUNDLE_VERSION = "research-report-v1"


def _canonical(value: Any) -> Any:
    """Strip volatile fields so a regenerated bundle hashes equally.

    Also coerces the scalar types SQLAlchemy hands back (``datetime``, ``Decimal``,
    numpy numbers) into JSON-native values: the bundle is stored in a JSON column,
    so a stray ``datetime`` would fail at INSERT time rather than at build time.
    """
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {
            key: _canonical(item)
            for key, item in value.items()
            if key not in {"generated_at", "created_at", "path", "storage_reference"}
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        try:
            return _canonical(item())
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return value
    return value


def build_bundle(
    *,
    project: dict,
    runs: list[dict],
    protocols: list[dict],
    results: list[dict],
    reference_areas: list[dict],
    plans: list[dict],
    scenes: list[dict],
    fusions: list[dict],
    disclaimer: dict,
    limitations: list[str],
) -> dict:
    """Assemble the machine-readable bundle."""
    included_runs = []
    excluded_runs = []
    for run in runs:
        entry = {
            "run_id": run.get("id"),
            "iteration": run.get("iteration"),
            "model_type": run.get("model_type"),
            "resolution": run.get("resolution"),
            "manifest_hash": run.get("manifest_hash"),
            "lineage_status": run.get("lineage_status"),
            "checkpoint_sha256": run.get("checkpoint_sha256"),
            "n_samples": run.get("n_samples"),
            "evaluation": run.get("evaluation"),
            "evaluation_strategy": run.get("evaluation_strategy"),
            "accuracy": run.get("accuracy"),
            "f1_macro": run.get("f1_macro"),
            "f1_weighted": run.get("f1_weighted"),
            "caveats": [],
        }
        if entry["lineage_status"] == "legacy":
            entry["caveats"].append(
                "run predates reproducibility manifests: its inputs cannot be identified by hash"
            )
            excluded_runs.append(entry)
        elif entry["lineage_status"] == "incomplete":
            entry["caveats"].append("manifest is incomplete (see the run's lineage record)")
            excluded_runs.append(entry)
        else:
            included_runs.append(entry)

    bundle = {
        "bundle_version": BUNDLE_VERSION,
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "classes": project.get("classes"),
            "taxonomy_version": (project.get("taxonomy") or {}).get("version"),
        },
        "runs": {"included": included_runs, "excluded": excluded_runs},
        "protocols": protocols,
        "results": results,
        "reference_areas": reference_areas,
        "plans": plans,
        "scenes": scenes,
        "fusions": fusions,
        "scientific_status": disclaimer,
        "limitations": limitations,
        "area_units": "m2 (hectares reported alongside)",
    }
    bundle = _canonical(bundle)
    bundle["digest"] = digest(_canonical(bundle))
    return bundle


def bundle_csv(bundle: dict) -> str:
    """One row per per-class metric, so the numbers are usable in a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "result_id",
            "protocol",
            "split_hash",
            "model_type",
            "resolution",
            "class",
            "support",
            "predicted",
            "precision",
            "recall",
            "f1",
            "iou",
            "undefined_metrics",
        ]
    )

    def render(value: Any) -> str:
        return "" if value is None else str(value)

    for result in bundle.get("results", []):
        metrics = result.get("metrics") or {}
        for row in metrics.get("per_class") or []:
            writer.writerow(
                [
                    result.get("id"),
                    result.get("protocol"),
                    result.get("split_hash"),
                    result.get("model_type"),
                    result.get("resolution"),
                    row.get("class_name"),
                    row.get("support"),
                    row.get("predicted"),
                    render(row.get("precision")),
                    render(row.get("recall")),
                    render(row.get("f1")),
                    render(row.get("iou")),
                    ";".join(sorted((row.get("undefined") or {}).keys())),
                ]
            )
    return buffer.getvalue()


def bundle_markdown(bundle: dict) -> str:
    """The human-readable summary. States what is *not* established."""
    project = bundle["project"]
    lines: list[str] = []
    add = lines.append
    add(f"# Research report — {project.get('name')} (#{project.get('id')})")
    add("")
    add(f"Bundle version `{bundle['bundle_version']}`, digest `{bundle.get('digest')}`.")
    add("")
    add("## Scientific status")
    add("")
    status = bundle["scientific_status"]
    add(f"- **Software validation:** {status['software_validation']}")
    add(f"- **Scientific validity:** {status['scientific_validity']}")
    add(f"- {status['detail']}")
    add("")
    add("## Evaluation protocols")
    add("")
    if not bundle["protocols"]:
        add("_No evaluation protocol has been declared for this project._")
    for protocol in bundle["protocols"]:
        add(
            f"- **#{protocol['id']} {protocol['protocol']}** — status `{protocol['status']}`, "
            f"split hash `{(protocol.get('split_hash') or '—')[:12]}`, "
            f"{protocol.get('train_count', 0)} train / {protocol.get('test_count', 0)} test samples"
        )
        for caveat in protocol.get("caveats") or []:
            add(f"  - {caveat}")
    add("")
    add("## Held-out results")
    add("")
    if not bundle["results"]:
        add("_No evaluation result has been recorded._")
    for result in bundle["results"]:
        metrics = result.get("metrics") or {}
        add(
            f"### Result #{result['id']} — {result.get('protocol')} / {result.get('model_type')}"
            f" ({result.get('resolution')})"
        )
        add("")
        add(f"- status: `{result.get('status')}`")
        add(f"- split hash: `{result.get('split_hash')}`")
        add(f"- n train / test: {metrics.get('n_train', '—')} / {metrics.get('n_test', '—')}")
        add(f"- accuracy: {_fmt(metrics.get('accuracy'))}")
        balanced = metrics.get("balanced_accuracy") or {}
        add(
            f"- balanced accuracy: {_fmt(balanced.get('value'))} "
            f"(classes used: {len(balanced.get('classes_used') or [])})"
        )
        add("")
        add("| class | support | precision | recall | F1 | IoU |")
        add("| --- | ---: | ---: | ---: | ---: | ---: |")
        for row in metrics.get("per_class") or []:
            add(
                f"| {row['class_name']} | {row['support']} | {_fmt(row.get('precision'))} | "
                f"{_fmt(row.get('recall'))} | {_fmt(row.get('f1'))} | {_fmt(row.get('iou'))} |"
            )
        undefined = [
            f"{row['class_name']}: {', '.join(sorted((row.get('undefined') or {}).keys()))}"
            for row in metrics.get("per_class") or []
            if row.get("undefined")
        ]
        if undefined:
            add("")
            add("Undefined metrics (reported as null, never as a perfect score):")
            for line in undefined:
                add(f"- {line}")
        calibration = result.get("calibration") or {}
        if calibration.get("available"):
            add("")
            add(
                f"- calibration: ECE {_fmt(calibration.get('expected_calibration_error'))}, "
                f"Brier {_fmt(calibration.get('brier_score'))} on "
                f"{calibration.get('n_samples')} held-out samples"
            )
        add("")
    add("## Runs")
    add("")
    add(f"Included (complete lineage): {len(bundle['runs']['included'])}")
    for run in bundle["runs"]["included"]:
        add(
            f"- run #{run['run_id']} iter {run['iteration']} {run['model_type']}/{run['resolution']}"
            f" — manifest `{(run.get('manifest_hash') or '—')[:12]}`, "
            f"accuracy {_fmt(run.get('accuracy'))}, F1 {_fmt(run.get('f1_macro'))}"
        )
    if bundle["runs"]["excluded"]:
        add("")
        add(f"Excluded (lineage not complete): {len(bundle['runs']['excluded'])}")
        for run in bundle["runs"]["excluded"]:
            add(f"- run #{run['run_id']}: {'; '.join(run.get('caveats') or [])}")
    add("")
    add("## Reference areas")
    add("")
    if not bundle["reference_areas"]:
        add(
            "_No independent reference area was supplied: mapped water areas are estimates and "
            "no area-error metric is reported._"
        )
    for area in bundle["reference_areas"]:
        add(
            f"- #{area['id']} scene {area.get('scene_id')}: {area['water_area_m2']:.0f} m² "
            f"from {area['source']} ({area['method']})"
        )
    add("")
    add("## Known limitations")
    add("")
    for limitation in bundle["limitations"]:
        add(f"- {limitation}")
    add("")
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def bundle_json(bundle: dict) -> str:
    return json.dumps(bundle, indent=2, sort_keys=True, default=str)
