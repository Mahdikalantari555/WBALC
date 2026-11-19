"""Model training endpoints (model-training capability)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from ..models import TrainingRun
from ..schemas import MetricsOut, RunSummaryOut, TrainRequest, TrainResponse
from ..services.pipeline import run_training
from ..services.schema_service import SchemaConflict
from ..services.training_service import TrainingError
from .deps import SessionDep, SettingsDep, get_project, latest_run

router = APIRouter(prefix="/projects/{project_id}", tags=["training"])


def run_to_metrics_out(run: TrainingRun) -> MetricsOut:
    m = run.metrics
    params = run.params or {}
    return MetricsOut(
        id=run.id,
        project_id=run.project_id,
        iteration=run.iteration,
        model_type=run.model_type,
        n_samples=run.n_samples,
        accuracy=m["accuracy"],
        f1_macro=m["f1_macro"],
        f1_weighted=m["f1_weighted"],
        confusion_matrix=m["confusion_matrix"],
        per_class=m["per_class"],
        classes=run.classes,
        evaluation=m.get("evaluation", "insufficient_train_metrics"),
        evaluation_details=m.get("evaluation_warning"),
        resolution=params.get("resolution", m.get("resolution", "patch")),
        evaluation_strategy=m.get("evaluation_strategy", params.get("evaluation_strategy")),
        n_train=m.get("n_train", run.n_samples),
        n_test=m.get("n_test"),
        held_out_groups=m.get("held_out_groups"),
        per_class_iou=m.get("per_class_iou", {}),
        created_at=run.created_at,
    )


def run_to_summary(run: TrainingRun) -> RunSummaryOut:
    """Metrics plus the lineage pointer, so a run list states its completeness."""
    base = run_to_metrics_out(run)
    manifest = run.manifest
    status = "legacy" if not manifest else ("complete" if manifest.get("complete") else "incomplete")
    return RunSummaryOut(
        **base.model_dump(),
        manifest_hash=(manifest or {}).get("hash"),
        lineage_status=status,
        experiment_id=run.experiment_id,
        checkpoint_sha256=run.checkpoint_sha256,
    )


@router.get("/runs", response_model=list[RunSummaryOut])
async def list_runs(project_id: int, session: SessionDep) -> list[RunSummaryOut]:
    """Every training run of the project, with lineage status per run."""
    await get_project(session, project_id)
    result = await session.execute(
        select(TrainingRun)
        .where(TrainingRun.project_id == project_id)
        .order_by(TrainingRun.iteration, TrainingRun.id)
    )
    return [run_to_summary(run) for run in result.scalars()]


@router.post("/train", response_model=TrainResponse, status_code=201)
async def train(project_id: int, payload: TrainRequest, session: SessionDep, settings: SettingsDep):
    """Train RF or LightGBM on the current labeled data (synchronous MVP)."""
    project = await get_project(session, project_id)
    try:
        run = await run_training(
            session,
            settings,
            project,
            model_type=payload.model_type,
            resolution=payload.resolution,
            evaluation_strategy=payload.evaluation_strategy,
            iteration=payload.iteration,
            test_size=payload.test_size,
            params=payload.params,
            accept_unverified_schema=payload.accept_unverified_schema,
        )
    except SchemaConflict as exc:
        # A schema conflict is a client-fixable configuration error, not a
        # "not enough data" condition, so it gets its own status.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TrainingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TrainResponse(
        id=run.id,
        project_id=run.project_id,
        iteration=run.iteration,
        model_type=run.model_type,
        resolution=(run.params or {}).get("resolution", "patch"),
        checkpoint=run.checkpoint_path,
        n_samples=run.n_samples,
        metrics=run_to_metrics_out(run),
    )


@router.get("/metrics", response_model=MetricsOut)
async def get_metrics(
    project_id: int,
    session: SessionDep,
    iteration: int | None = Query(default=None, ge=0),
):
    """Metrics of the latest training run (or a specific iteration)."""
    await get_project(session, project_id)
    run = await latest_run(session, project_id, iteration)
    if run is None:
        raise HTTPException(status_code=404, detail="No training run found; train a model first")
    return run_to_metrics_out(run)


@router.get("/metrics/history", response_model=list[MetricsOut])
async def metrics_history(project_id: int, session: SessionDep):
    """Metrics for every training run, oldest first."""
    await get_project(session, project_id)
    result = await session.execute(
        select(TrainingRun).where(TrainingRun.project_id == project_id).order_by(TrainingRun.id)
    )
    return [run_to_metrics_out(run) for run in result.scalars()]
