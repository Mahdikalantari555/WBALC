"""Lineage, artifact integrity and experiment endpoints (Phase 3).

The guiding rule: a comparison may only present scores side by side when the
inputs behind them are the same. Where they differ, the difference is listed
rather than averaged away, and a run whose provenance is unavailable says so.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Experiment, TrainingRun
from ..schemas import (
    ExperimentCreate,
    ExperimentMembership,
    ExperimentOut,
    ExperimentUpdate,
    RunComparisonOut,
    RunComparisonRow,
    RunLineageOut,
)
from ..services.lineage_service import IntegrityError, verify_artifact
from .deps import SessionDep, get_project

router = APIRouter(prefix="/projects/{project_id}", tags=["lineage"])


def _experiment_out(experiment: Experiment) -> ExperimentOut:
    return ExperimentOut(
        id=experiment.id,
        project_id=experiment.project_id,
        name=experiment.name,
        description=experiment.description or "",
        hypothesis=experiment.hypothesis,
        config=experiment.config,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        run_ids=sorted(run.id for run in experiment.runs),
    )


async def _get_experiment(session, project_id: int, experiment_id: int) -> Experiment:
    result = await session.execute(
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.project_id == project_id)
    )
    experiment = result.scalar_one_or_none()
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    return experiment


def _lineage_status(run: TrainingRun) -> tuple[str, dict | None, list[str]]:
    """Classify a run's record without inventing what is missing.

    - `legacy`: created before manifests existed. Nothing is back-filled.
    - `incomplete`: a manifest exists but names the pieces it could not prove.
    - `complete`: every input has content identity and the code revision is known.
    """
    manifest = run.manifest
    if not manifest:
        return "legacy", None, ["run manifest", "input content hashes", "label version snapshot"]
    missing = list(manifest.get("missing") or [])
    return ("complete" if manifest.get("complete") else "incomplete"), manifest, missing


@router.get("/runs/{run_id}/lineage", response_model=RunLineageOut)
async def run_lineage(project_id: int, run_id: int, session: SessionDep) -> RunLineageOut:
    """The reproducibility record of one run, including what it lacks."""
    await get_project(session, project_id)
    run = await session.get(TrainingRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Training run {run_id} not found")

    status, manifest, missing = _lineage_status(run)
    notes: list[str] = []
    artifact: dict | None = None
    if run.checkpoint_sha256:
        try:
            artifact = await anyio.to_thread.run_sync(
                lambda: verify_artifact(run.checkpoint_path, run.checkpoint_sha256)
            )
            artifact["path_name"] = run.checkpoint_path.rsplit("/", 1)[-1]
        except IntegrityError as exc:
            artifact = {"verified": False, "reason": str(exc)}
    else:
        notes.append(
            "No checkpoint checksum was recorded for this run; its artifact cannot be proven unmodified."
        )
    if status == "legacy":
        notes.append(
            "This run predates reproducibility manifests. Its inputs, label versions and code "
            "revision are unavailable and are deliberately not reconstructed."
        )

    return RunLineageOut(
        run_id=run.id,
        iteration=run.iteration,
        experiment_id=run.experiment_id,
        lineage_status=status,
        manifest=manifest,
        manifest_hash=(manifest or {}).get("hash"),
        missing=missing,
        artifact=artifact,
        notes=notes,
    )


@router.get("/experiments", response_model=list[ExperimentOut])
async def list_experiments(project_id: int, session: SessionDep) -> list[ExperimentOut]:
    await get_project(session, project_id)
    result = await session.execute(
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.project_id == project_id)
        .order_by(Experiment.id.desc())
    )
    return [_experiment_out(experiment) for experiment in result.scalars().unique()]


@router.post("/experiments", response_model=ExperimentOut, status_code=201)
async def create_experiment(
    project_id: int, payload: ExperimentCreate, session: SessionDep
) -> ExperimentOut:
    await get_project(session, project_id)
    experiment = Experiment(
        project_id=project_id,
        name=payload.name.strip(),
        description=payload.description,
        hypothesis=payload.hypothesis,
        config=payload.config,
    )
    session.add(experiment)
    await session.commit()
    await session.refresh(experiment)
    result = await session.execute(
        select(Experiment).options(selectinload(Experiment.runs)).where(Experiment.id == experiment.id)
    )
    return _experiment_out(result.scalar_one())


@router.patch("/experiments/{experiment_id}", response_model=ExperimentOut)
async def update_experiment(
    project_id: int, experiment_id: int, payload: ExperimentUpdate, session: SessionDep
) -> ExperimentOut:
    """Rename or re-describe a group. Runs and their manifests are untouched."""
    await get_project(session, project_id)
    experiment = await _get_experiment(session, project_id, experiment_id)
    for field in ("name", "description", "hypothesis", "config"):
        value = getattr(payload, field)
        if value is not None:
            setattr(experiment, field, value)
    await session.commit()
    await session.refresh(experiment)
    return _experiment_out(experiment)


@router.delete("/experiments/{experiment_id}", status_code=204)
async def delete_experiment(project_id: int, experiment_id: int, session: SessionDep) -> None:
    """Remove the grouping only; the runs (and their history) survive."""
    await get_project(session, project_id)
    experiment = await _get_experiment(session, project_id, experiment_id)
    for run in list(experiment.runs):
        run.experiment_id = None
    await session.delete(experiment)
    await session.commit()


@router.post("/experiments/{experiment_id}/runs", response_model=ExperimentOut)
async def add_runs(
    project_id: int,
    experiment_id: int,
    payload: ExperimentMembership,
    session: SessionDep,
) -> ExperimentOut:
    """Associate existing runs with an experiment.

    Only the association is written: `run.manifest`, metrics and the checkpoint are
    never modified by grouping, so membership cannot rewrite history.
    """
    await get_project(session, project_id)
    experiment = await _get_experiment(session, project_id, experiment_id)
    result = await session.execute(
        select(TrainingRun).where(
            TrainingRun.project_id == project_id, TrainingRun.id.in_(payload.training_run_ids)
        )
    )
    runs = list(result.scalars())
    found = {run.id for run in runs}
    unknown = [str(run_id) for run_id in payload.training_run_ids if run_id not in found]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Training runs not in this project: {', '.join(unknown)}",
        )
    for run in runs:
        if run.experiment_id not in (None, experiment_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Run {run.id} already belongs to experiment {run.experiment_id}; "
                    "remove it there first rather than moving it silently."
                ),
            )
        run.experiment_id = experiment_id
    await session.commit()
    await session.refresh(experiment)
    return _experiment_out(experiment)


@router.delete("/experiments/{experiment_id}/runs/{run_id}", response_model=ExperimentOut)
async def remove_run(
    project_id: int, experiment_id: int, run_id: int, session: SessionDep
) -> ExperimentOut:
    await get_project(session, project_id)
    experiment = await _get_experiment(session, project_id, experiment_id)
    run = await session.get(TrainingRun, run_id)
    if run is None or run.project_id != project_id or run.experiment_id != experiment_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} is not in experiment {experiment_id}")
    run.experiment_id = None
    await session.commit()
    await session.refresh(experiment)
    return _experiment_out(experiment)


def _row(run: TrainingRun) -> tuple[RunComparisonRow, dict | None, str]:
    status, manifest, _ = _lineage_status(run)
    params = run.params or {}
    metrics = run.metrics or {}
    inputs = {
        str(entry.get("dataset_id")): entry.get("content_sha256")
        for entry in (manifest or {}).get("inputs", [])
    }
    row = RunComparisonRow(
        run_id=run.id,
        iteration=run.iteration,
        model_type=run.model_type,
        accuracy=metrics.get("accuracy"),
        f1_macro=metrics.get("f1_macro"),
        n_samples=run.n_samples,
        evaluation=metrics.get("evaluation") or params.get("evaluation_strategy"),
        lineage_status=status,
        manifest_hash=(manifest or {}).get("hash"),
        label_snapshot_hash=((manifest or {}).get("labels") or {}).get("hash"),
        input_hashes=inputs,
        config={
            "resolution": params.get("resolution"),
            "evaluation_strategy": params.get("evaluation_strategy"),
            "random_state": params.get("random_state"),
            "test_size": params.get("test_size"),
            "model_type": run.model_type,
            "bands": params.get("bands"),
            "trained_classes": run.trained_classes or run.classes,
        },
        environment_revision=((manifest or {}).get("environment") or {}).get("revision"),
    )
    return row, manifest, status


def _compare(runs: list[TrainingRun], project_id: int, experiment_id: int | None) -> RunComparisonOut:
    rows: list[RunComparisonRow] = []
    manifests: dict[int, dict | None] = {}
    statuses: dict[int, str] = {}
    for run in runs:
        row, manifest, status = _row(run)
        rows.append(row)
        manifests[run.id] = manifest
        statuses[run.id] = status

    differences: dict[str, list] = {}
    caveats: list[str] = []

    def differs(name: str, values: list) -> None:
        if len({repr(value) for value in values}) > 1:
            differences[name] = values

    differs("input_hashes", [row.input_hashes for row in rows])
    differs("label_snapshot_hash", [row.label_snapshot_hash for row in rows])
    differs("model_type", [row.model_type for row in rows])
    differs("n_samples", [row.n_samples for row in rows])
    differs(
        "config",
        [
            {k: v for k, v in row.config.items() if k != "trained_classes"}
            for row in rows
        ],
    )
    # Two runs can share the engine's evaluation label while having been asked
    # for different protocols; both are compared.
    differs(
        "evaluation",
        [(row.evaluation, row.config.get("evaluation_strategy")) for row in rows],
    )
    differs("environment_revision", [row.environment_revision for row in rows])

    if any(statuses[run.id] == "legacy" for run in runs):
        caveats.append(
            "At least one run predates reproducibility manifests: its inputs and label "
            "versions are unknown, so it cannot be compared as if they matched."
        )
    if len(rows) < 2:
        caveats.append("Only one run is in scope: there is nothing to compare it against.")
    elif not differences:
        caveats.append(
            "These runs recorded identical inputs, labels, model configuration and environment; "
            "differences in score are therefore attributable to model randomness or iteration."
        )
    if "evaluation" in differences:
        caveats.append(
            "The evaluation protocols differ (for example a random holdout against a spatial "
            "block holdout); their scores are not on the same scale."
        )
    if "input_hashes" in differences:
        caveats.append("The runs used different input bytes; this is a comparison of data, not of models.")
    if "label_snapshot_hash" in differences:
        caveats.append("The runs trained on different label versions.")

    complete = all(statuses[run.id] == "complete" for run in runs)
    # A single run is never "comparable": there is no second side to the comparison.
    comparable = bool(len(rows) >= 2 and complete and not differences)
    return RunComparisonOut(
        experiment_id=experiment_id,
        project_id=project_id,
        runs=rows,
        differences=differences,
        comparable=comparable,
        caveats=caveats,
    )


@router.get("/experiments/{experiment_id}/compare", response_model=RunComparisonOut)
async def compare_experiment(
    project_id: int, experiment_id: int, session: SessionDep
) -> RunComparisonOut:
    """Compare the runs in an experiment, stating where the inputs differ."""
    await get_project(session, project_id)
    experiment = await _get_experiment(session, project_id, experiment_id)
    runs = sorted(experiment.runs, key=lambda run: (run.iteration, run.id))
    if len(runs) < 1:
        raise HTTPException(status_code=409, detail="Experiment has no runs to compare")
    return _compare(runs, project_id, experiment_id)


@router.get("/compare", response_model=RunComparisonOut)
async def compare_runs(
    project_id: int,
    session: SessionDep,
    run_ids: str | None = None,
) -> RunComparisonOut:
    """Compare an explicit set of runs (`run_ids=1,2,3`), else the whole project."""
    await get_project(session, project_id)
    stmt = select(TrainingRun).where(TrainingRun.project_id == project_id)
    if run_ids:
        try:
            wanted = [int(part) for part in run_ids.split(",") if part.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="run_ids must be comma-separated integers") from exc
        stmt = stmt.where(TrainingRun.id.in_(wanted))
    result = await session.execute(stmt.order_by(TrainingRun.iteration, TrainingRun.id))
    runs = list(result.scalars())
    if not runs:
        raise HTTPException(status_code=409, detail="No training runs to compare")
    return _compare(runs, project_id, None)
