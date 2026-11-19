"""Research evaluation, reference areas, plans and report bundles (Phase 5).

The router's contract:

- A protocol is **persisted with its membership**, so a report generated later
  describes the exact partition that produced the score.
- An evaluation result never replaces a training metric: it is a separate fit on
  the training partition, scored on the held-out partition, and says so.
- Area error needs an operator-supplied reference; without one the mapped area is
  reported as an estimate and **no error metric is produced**.
- Reports are regenerable: same records → same digest.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select

from ..models import (
    Dataset,
    EvaluationProtocol,
    EvaluationResult,
    Project,
    ReferenceArea,
    ResearchPlan,
    ResearchReport,
    Scene,
    TrainingRun,
    utcnow,
)
from ..schemas import (
    ProtocolDetailOut,
    ProtocolOut,
    ProtocolRequest,
    EvaluationRequest,
    EvaluationResultOut,
    ReferenceAreaCreate,
    ReferenceAreaOut,
    AreaComparisonOut,
    ResearchPlanCreate,
    ResearchPlanOut,
    PlanComparisonRequest,
    PlanComparisonOut,
    ReportOut,
    ReportDetailOut,
    ReportRequest,
    ScientificStatusOut,
)
from ..services.metrics_service import area_error, scene_distribution
from ..services.protocol_service import ProtocolError, build_split, sample_records
from ..services.research_service import (
    ResearchError,
    build_result,
    research_disclaimer,
    score_protocol,
    split_for_project,
)
from ..services.report_service import (
    bundle_csv,
    bundle_json,
    bundle_markdown,
    build_bundle,
    finalize_bundle,
)
from ..storage import project_dir
from .deps import SessionDep, SettingsDep, get_project, project_labels

router = APIRouter(prefix="/projects/{project_id}/research", tags=["research"])


# ------------------------------------------------------------------ helpers
async def _datasets(session, project_id: int) -> dict[int, Dataset]:
    result = await session.execute(select(Dataset).where(Dataset.project_id == project_id))
    return {row.id: row for row in result.scalars()}


async def _scenes(session, project_id: int) -> dict[int, Scene]:
    result = await session.execute(select(Scene).where(Scene.project_id == project_id))
    return {row.id: row for row in result.scalars()}


def _protocol_out(protocol: EvaluationProtocol) -> dict:
    split = protocol.split or {}
    return {
        "id": protocol.id,
        "project_id": protocol.project_id,
        "name": protocol.name,
        "protocol": protocol.protocol,
        "status": protocol.status,
        "reason": protocol.reason,
        "configuration": protocol.configuration or {},
        "train_count": split.get("train_count", 0),
        "test_count": split.get("test_count", 0),
        "held_out_groups": split.get("held_out_groups", []),
        "split_hash": protocol.split_hash,
        "caveats": protocol.caveats or [],
        "created_at": protocol.created_at,
    }


def _result_out(result: EvaluationResult, protocol_name: str | None = None) -> dict:
    return {
        "id": result.id,
        "project_id": result.project_id,
        "protocol_id": result.protocol_id,
        "protocol": protocol_name,
        "split_hash": result.protocol_split_hash,
        "model_type": result.model_type,
        "resolution": result.resolution,
        "config": result.config or {},
        "metrics": result.metrics or {},
        "calibration": result.calibration or {},
        "coverage": result.coverage or {},
        "status": result.status,
        "caveats": result.caveats or [],
        "created_at": result.created_at,
    }


# ---------------------------------------------------------------- protocols
@router.post("/protocols", response_model=ProtocolDetailOut, status_code=201)
async def create_protocol(
    project_id: int, payload: ProtocolRequest, session: SessionDep
):
    """Declare and persist an evaluation split; insufficient data is reported, not faked."""
    project = await get_project(session, project_id)
    labels = await project_labels(session, project_id)
    datasets = await _datasets(session, project_id)
    group_map = {
        int(key): value for key, value in (payload.groups or {}).items() if key.isdigit()
    }
    samples = sample_records(
        [label for label in labels], datasets, list(project.classes), group_map=group_map
    )
    try:
        split = split_for_project(
            samples,
            protocol=payload.protocol,
            seed=payload.seed,
            test_size=payload.test_size,
            block_size=payload.block_size,
            buffer=payload.buffer,
            spatial_unit=payload.spatial_unit,
        )
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Records are kept in the stored split so scoring does not re-resolve them from
    # a label table that may have changed since the protocol was declared.
    by_id = {sample["sample_id"]: sample for sample in samples}
    split["train_records"] = [by_id[sid] for sid in split["train"] if sid in by_id]
    split["test_records"] = [by_id[sid] for sid in split["test"] if sid in by_id]

    protocol = EvaluationProtocol(
        project_id=project_id,
        name=payload.name or f"{payload.protocol} split (seed {payload.seed})",
        protocol=payload.protocol,
        status=split["status"],
        reason=split.get("reason"),
        configuration=split.get("configuration") or {},
        split=split,
        split_hash=split.get("split_hash"),
        caveats=split.get("caveats") or [],
        created_at=utcnow(),
    )
    session.add(protocol)
    await session.commit()
    await session.refresh(protocol)
    return ProtocolDetailOut(**_protocol_out(protocol), split=protocol.split)


@router.get("/protocols", response_model=list[ProtocolOut])
async def list_protocols(project_id: int, session: SessionDep):
    await get_project(session, project_id)
    result = await session.execute(
        select(EvaluationProtocol)
        .where(EvaluationProtocol.project_id == project_id)
        .order_by(EvaluationProtocol.id)
    )
    return [ProtocolOut(**_protocol_out(row)) for row in result.scalars()]


@router.get("/protocols/{protocol_id}", response_model=ProtocolDetailOut)
async def get_protocol(project_id: int, protocol_id: int, session: SessionDep):
    protocol = await session.get(EvaluationProtocol, protocol_id)
    if protocol is None or protocol.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Protocol {protocol_id} not found")
    return ProtocolDetailOut(**_protocol_out(protocol), split=protocol.split or {})


# --------------------------------------------------------------- evaluation
@router.post("/evaluations", response_model=EvaluationResultOut, status_code=201)
async def run_evaluation(
    project_id: int,
    payload: EvaluationRequest,
    session: SessionDep,
    settings: SettingsDep,
):
    """Fit on the protocol's training partition and score the held-out partition."""
    project = await get_project(session, project_id)
    protocol = await session.get(EvaluationProtocol, payload.protocol_id)
    if protocol is None or protocol.project_id != project_id:
        raise HTTPException(
            status_code=404, detail=f"Protocol {payload.protocol_id} not found in project {project_id}"
        )
    datasets = await _datasets(session, project_id)
    split = dict(protocol.split or {})
    if protocol.status != "ok":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Protocol {protocol.id} is '{protocol.status}': {protocol.reason}. No score can be "
                "produced from a split the data cannot support."
            ),
        )
    try:
        scored = await score_protocol(
            project_id=project_id,
            split=split,
            datasets=datasets,
            class_names=list(project.classes),
            settings=settings,
            model_type=payload.model_type,
            resolution=payload.resolution,
            params=payload.params,
            checkpoint_dir=project_dir(settings, "models", project_id),
        )
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = build_result(
        project_id=project_id,
        protocol_id=protocol.id,
        split=split,
        scored=scored,
        model_type=payload.model_type,
        resolution=payload.resolution,
        params=payload.params,
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return EvaluationResultOut(**_result_out(result, protocol.protocol))


@router.get("/evaluations", response_model=list[EvaluationResultOut])
async def list_evaluations(project_id: int, session: SessionDep):
    await get_project(session, project_id)
    protocols = {
        row.id: row for row in (
            await session.execute(
                select(EvaluationProtocol).where(EvaluationProtocol.project_id == project_id)
            )
        ).scalars()
    }
    result = await session.execute(
        select(EvaluationResult)
        .where(EvaluationResult.project_id == project_id)
        .order_by(EvaluationResult.id)
    )
    return [
        EvaluationResultOut(
            **_result_out(row, protocols[row.protocol_id].protocol if row.protocol_id in protocols else None)
        )
        for row in result.scalars()
    ]


# ----------------------------------------------------------- reference areas
@router.post("/reference-areas", response_model=ReferenceAreaOut, status_code=201)
async def add_reference_area(
    project_id: int, payload: ReferenceAreaCreate, session: SessionDep
):
    """Record an operator-supplied independent water area.

    The engine cannot invent a reference, so the source and measurement method are
    required fields rather than free-form notes.
    """
    await get_project(session, project_id)
    if payload.scene_id is not None:
        scene = await session.get(Scene, payload.scene_id)
        if scene is None or scene.project_id != project_id:
            raise HTTPException(
                status_code=404, detail=f"Scene {payload.scene_id} not found in project {project_id}"
            )
    record = ReferenceArea(
        project_id=project_id,
        scene_id=payload.scene_id,
        label=payload.label,
        water_area_m2=payload.water_area_m2,
        source=payload.source,
        method=payload.method,
        uncertainty_m2=payload.uncertainty_m2,
        notes=payload.notes,
        created_at=utcnow(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.get("/reference-areas", response_model=list[ReferenceAreaOut])
async def list_reference_areas(project_id: int, session: SessionDep):
    await get_project(session, project_id)
    result = await session.execute(
        select(ReferenceArea)
        .where(ReferenceArea.project_id == project_id)
        .order_by(ReferenceArea.id)
    )
    return list(result.scalars())


@router.get("/area-error", response_model=list[AreaComparisonOut])
async def area_error_report(project_id: int, session: SessionDep):
    """Mapped water area vs the operator's reference, per scene that has and needs one."""
    await get_project(session, project_id)
    from ..models import SceneAnalysis

    references = list(
        (
            await session.execute(
                select(ReferenceArea).where(ReferenceArea.project_id == project_id)
            )
        ).scalars()
    )
    if not references:
        raise HTTPException(
            status_code=409,
            detail=(
                "No independent reference area has been supplied for this project, so no "
                "area-error metric is produced. Mapped areas remain estimates."
            ),
        )
    by_scene = {row.scene_id: row for row in references}
    analyses = list(
        (
            await session.execute(
                select(SceneAnalysis).where(SceneAnalysis.project_id == project_id)
            )
        ).scalars()
    )
    rows = []
    for analysis in analyses:
        reference = by_scene.get(analysis.scene_id)
        if reference is None:
            continue
        water = (analysis.areas or {}).get("water")
        if not water:
            continue
        try:
            error = area_error(
                float(water["area_m2"]),
                float(reference.water_area_m2),
                reference_source=reference.source,
                reference_method=reference.method,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        rows.append(
            {
                "scene_id": analysis.scene_id,
                "analysis_id": analysis.id,
                **error,
            }
        )
    if not rows:
        raise HTTPException(
            status_code=409,
            detail=(
                "A reference area exists, but no classified scene has a derived water area to "
                "compare it with yet."
            ),
        )
    return rows


@router.get("/scene-spread")
async def scene_spread(project_id: int, session: SessionDep):
    """Water area per scene as a scene-level distribution, not a pixel pool."""
    await get_project(session, project_id)
    from ..models import SceneAnalysis

    analyses = list(
        (
            await session.execute(
                select(SceneAnalysis).where(SceneAnalysis.project_id == project_id)
            )
        ).scalars()
    )
    values = []
    regions = []
    for analysis in analyses:
        water = (analysis.areas or {}).get("water")
        if not water:
            continue
        values.append(float(water["area_m2"]))
        regions.append(f"scene:{analysis.scene_id}")
    if not values:
        raise HTTPException(
            status_code=409,
            detail="No classified scene has a derived water area yet; there is nothing to aggregate.",
        )
    return scene_distribution(values, regions)


# ------------------------------------------------------------- research plans
@router.post("/plans", response_model=ResearchPlanOut, status_code=201)
async def create_plan(project_id: int, payload: ResearchPlanCreate, session: SessionDep):
    await get_project(session, project_id)
    if payload.protocol_id is not None:
        protocol = await session.get(EvaluationProtocol, payload.protocol_id)
        if protocol is None or protocol.project_id != project_id:
            raise HTTPException(
                status_code=404,
                detail=f"Protocol {payload.protocol_id} not found in project {project_id}",
            )
    plan = ResearchPlan(
        project_id=project_id,
        name=payload.name,
        hypothesis=payload.hypothesis,
        protocol_id=payload.protocol_id,
        comparison_metric=payload.comparison_metric,
        factors=payload.factors,
        repetitions=payload.repetitions,
        resource_limits=payload.resource_limits,
        notes=payload.notes,
        created_at=utcnow(),
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@router.get("/plans", response_model=list[ResearchPlanOut])
async def list_plans(project_id: int, session: SessionDep):
    await get_project(session, project_id)
    result = await session.execute(
        select(ResearchPlan).where(ResearchPlan.project_id == project_id).order_by(ResearchPlan.id)
    )
    return list(result.scalars())


@router.post("/plans/compare", response_model=PlanComparisonOut)
async def compare_plan(
    project_id: int, payload: PlanComparisonRequest, session: SessionDep
):
    """Compare results inside a plan, exposing shared and differing factors."""
    await get_project(session, project_id)
    plan = await session.get(ResearchPlan, payload.plan_id)
    if plan is None or plan.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Plan {payload.plan_id} not found")

    query = select(EvaluationResult).where(EvaluationResult.project_id == project_id)
    if payload.result_ids:
        query = query.where(EvaluationResult.id.in_(payload.result_ids))
    elif plan.protocol_id is not None:
        query = query.where(EvaluationResult.protocol_id == plan.protocol_id)
    results = list((await session.execute(query.order_by(EvaluationResult.id))).scalars())
    if not results:
        raise HTTPException(
            status_code=409, detail="This plan has no evaluation results to compare yet."
        )

    fields = ("protocol_id", "protocol_split_hash", "model_type", "resolution", "seed", "params")
    shared: dict = {}
    differing: dict = {}
    for field in fields:
        values = []
        for result in results:
            if field == "seed" or field == "params":
                values.append((result.config or {}).get(field))
            else:
                values.append(getattr(result, field, None))
        unique = {repr(value) for value in values}
        (shared if len(unique) == 1 else differing)[field] = values[0] if len(unique) == 1 else values

    metric = plan.comparison_metric
    rows = []
    for result in results:
        metrics = result.metrics or {}
        if metric in ("accuracy",):
            value = metrics.get("accuracy")
        elif metric in ("f1_macro", "f1_weighted"):
            value = metrics.get("weighted", {}).get("f1") if metric == "f1_weighted" else (metrics.get("macro", {}).get("f1") or {}).get("value")
        elif metric == "balanced_accuracy":
            value = (metrics.get("balanced_accuracy") or {}).get("value")
        else:
            value = metrics.get(metric)
        rows.append(
            {
                "result_id": result.id,
                "model_type": result.model_type,
                "resolution": result.resolution,
                "status": result.status,
                "value": value,
                "n_test": metrics.get("n_test"),
            }
        )

    paired = not differing.get("protocol_split_hash") and bool(
        shared.get("protocol_split_hash")
    )
    caveats = []
    if not paired:
        caveats.append(
            "These results were not scored on the same persisted split, so they are presented "
            "side by side, not as a paired comparison."
        )
    if differing.get("seed"):
        caveats.append(
            "Seeds differ between results; a difference in score cannot be attributed to the "
            "factor alone."
        )
    if differing.get("resolution"):
        caveats.append("Feature resolution differs (patch summaries vs per-pixel values).")
    caveats.append(
        "Repetitions here are repeated fits, not independent scenes: they do not measure "
        "sampling variability of the landscape."
    )
    return PlanComparisonOut(
        plan_id=plan.id,
        comparison_metric=metric,
        results=rows,
        factors=plan.factors or [],
        shared=shared,
        differing=differing,
        paired=paired,
        caveats=caveats,
    )


# -------------------------------------------------------------- report bundle
async def _report_payload(session, settings, project_id: int) -> tuple[dict, dict]:
    project = await get_project(session, project_id)
    runs = list(
        (
            await session.execute(
                select(TrainingRun)
                .where(TrainingRun.project_id == project_id)
                .order_by(TrainingRun.iteration, TrainingRun.id)
            )
        ).scalars()
    )
    protocols = list(
        (
            await session.execute(
                select(EvaluationProtocol)
                .where(EvaluationProtocol.project_id == project_id)
                .order_by(EvaluationProtocol.id)
            )
        ).scalars()
    )
    results = list(
        (
            await session.execute(
                select(EvaluationResult)
                .where(EvaluationResult.project_id == project_id)
                .order_by(EvaluationResult.id)
            )
        ).scalars()
    )
    references = list(
        (
            await session.execute(
                select(ReferenceArea).where(ReferenceArea.project_id == project_id)
            )
        ).scalars()
    )
    plans = list(
        (
            await session.execute(
                select(ResearchPlan).where(ResearchPlan.project_id == project_id)
            )
        ).scalars()
    )
    scenes = list(
        (
            await session.execute(select(Scene).where(Scene.project_id == project_id))
        ).scalars()
    )
    from ..models import FusionRun

    fusions = list(
        (
            await session.execute(
                select(FusionRun).where(FusionRun.project_id == project_id)
            )
        ).scalars()
    )

    protocol_names = {row.id: row.protocol for row in protocols}
    run_payload = []
    for run in runs:
        manifest = run.manifest or {}
        run_payload.append(
            {
                "id": run.id,
                "iteration": run.iteration,
                "model_type": run.model_type,
                "resolution": (run.params or {}).get("resolution", "patch"),
                "manifest_hash": manifest.get("hash"),
                "lineage_status": "legacy"
                if not manifest
                else ("complete" if manifest.get("complete") else "incomplete"),
                "checkpoint_sha256": run.checkpoint_sha256,
                "n_samples": run.n_samples,
                "evaluation": (run.metrics or {}).get("evaluation"),
                "evaluation_strategy": (run.params or {}).get("evaluation_strategy"),
                "accuracy": (run.metrics or {}).get("accuracy"),
                "f1_macro": (run.metrics or {}).get("f1_macro"),
                "f1_weighted": (run.metrics or {}).get("f1_weighted"),
            }
        )

    bundle = build_bundle(
        project={
            "id": project.id,
            "name": project.name,
            "classes": list(project.classes),
            "taxonomy": project.taxonomy,
        },
        runs=run_payload,
        protocols=[
            {
                "id": row.id,
                "name": row.name,
                "protocol": row.protocol,
                "status": row.status,
                "reason": row.reason,
                "split_hash": row.split_hash,
                "train_count": (row.split or {}).get("train_count", 0),
                "test_count": (row.split or {}).get("test_count", 0),
                "configuration": row.configuration,
                "caveats": row.caveats,
            }
            for row in protocols
        ],
        results=[
            {
                "id": row.id,
                "protocol": protocol_names.get(row.protocol_id),
                "split_hash": row.protocol_split_hash,
                "model_type": row.model_type,
                "resolution": row.resolution,
                "status": row.status,
                "metrics": row.metrics,
                "calibration": row.calibration,
                "coverage": row.coverage,
                "caveats": row.caveats,
            }
            for row in results
        ],
        reference_areas=[
            {
                "id": row.id,
                "scene_id": row.scene_id,
                "label": row.label,
                "water_area_m2": row.water_area_m2,
                "source": row.source,
                "method": row.method,
                "uncertainty_m2": row.uncertainty_m2,
            }
            for row in references
        ],
        plans=[
            {
                "id": row.id,
                "name": row.name,
                "hypothesis": row.hypothesis,
                "comparison_metric": row.comparison_metric,
                "factors": row.factors,
                "repetitions": row.repetitions,
            }
            for row in plans
        ],
        scenes=[
            {
                "id": row.id,
                "sensor": row.sensor,
                "acquisition_datetime": row.acquisition_datetime,
                "content_sha256": row.content_sha256,
                "crs": row.crs,
                "width": row.width,
                "height": row.height,
            }
            for row in scenes
        ],
        fusions=[
            {
                "id": row.id,
                "rule": row.rule,
                "weights": row.weights,
                "sources": (row.lineage or {}).get("sources"),
                "missing_policy": row.missing_policy,
                "fusion_digest": (row.lineage or {}).get("fusion_digest"),
            }
            for row in fusions
        ],
        disclaimer=research_disclaimer(),
        limitations=_limitations(protocols, results, references, runs),
    )
    return bundle, {"project": project}


def _limitations(protocols, results, references, runs) -> list[str]:
    limitations = [
        "No real satellite imagery was evaluated here; every number comes from the project's own data.",
        "Reported accuracy is conditional on the declared protocol; it is not a claim about water mapping in general.",
    ]
    if not references:
        limitations.append(
            "No independent reference area was supplied: mapped water areas are estimates and no area-error metric exists."
        )
    if not results:
        limitations.append(
            "No held-out evaluation result has been recorded, so no validated score exists for this project."
        )
    insufficient = [row for row in protocols if row.status != "ok"]
    if insufficient:
        limitations.append(
            f"{len(insufficient)} declared protocol(s) could not support an independent split: "
            + "; ".join(f"#{row.id} {row.protocol} ({row.reason})" for row in insufficient)
        )
    legacy = [row for row in runs if not row.manifest]
    if legacy:
        limitations.append(
            f"{len(legacy)} run(s) predate reproducibility manifests and are excluded from the "
            "report's evidence list."
        )
    limitations.append(
        "Repetitions and seeds measure fit variability only; they are not independent landscape samples."
    )
    return limitations


@router.post("/reports", response_model=ReportOut, status_code=201)
async def create_report(
    project_id: int, payload: ReportRequest, session: SessionDep, settings: SettingsDep
):
    """Generate a checksum-linked JSON/CSV/Markdown bundle from stored records."""
    bundle, _ = await _report_payload(session, settings, project_id)
    title = payload.title or f"Research report — project #{project_id}"
    bundle = finalize_bundle(bundle, title)

    out_dir = project_dir(settings, "reports", project_id)
    tag = uuid.uuid4().hex[:8]
    files = {
        "json": out_dir / f"research-report-{tag}.json",
        "csv": out_dir / f"research-report-{tag}.csv",
        "markdown": out_dir / f"research-report-{tag}.md",
    }

    def _write():
        files["json"].write_text(bundle_json(bundle), encoding="utf-8")
        files["csv"].write_text(bundle_csv(bundle), encoding="utf-8")
        files["markdown"].write_text(bundle_markdown(bundle), encoding="utf-8")

    await anyio.to_thread.run_sync(_write)

    from ..services.lineage_service import file_identity

    artifacts = {}
    media = {"json": "application/json", "csv": "text/csv", "markdown": "text/markdown"}
    for kind, path in files.items():
        identity = await anyio.to_thread.run_sync(lambda p=path: file_identity(p))
        artifacts[kind] = {
            "path": str(path),
            "name": path.name,
            "sha256": (identity or {}).get("sha256"),
            "size_bytes": (identity or {}).get("size_bytes"),
            "media_type": media[kind],
        }

    record = ResearchReport(
        project_id=project_id,
        title=title,
        status="complete",
        bundle=bundle,
        artifacts=artifacts,
        caveats=bundle.get("limitations") or [],
        digest=bundle.get("digest"),
        created_at=utcnow(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return _report_out(record)


def _report_out(record: ResearchReport) -> dict:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "title": record.title,
        "status": record.status,
        "digest": record.digest,
        "artifacts": record.artifacts or {},
        "caveats": record.caveats or [],
        "scientific_status": (record.bundle or {}).get("scientific_status")
        or research_disclaimer(),
        "created_at": record.created_at,
    }


@router.get("/reports", response_model=list[ReportOut])
async def list_reports(project_id: int, session: SessionDep):
    await get_project(session, project_id)
    result = await session.execute(
        select(ResearchReport)
        .where(ResearchReport.project_id == project_id)
        .order_by(ResearchReport.id)
    )
    return [_report_out(row) for row in result.scalars()]


@router.get("/reports/{report_id}", response_model=ReportDetailOut)
async def get_report(project_id: int, report_id: int, session: SessionDep):
    record = await session.get(ResearchReport, report_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return ReportDetailOut(**_report_out(record), bundle=record.bundle or {})


@router.get("/reports/{report_id}/files/{kind}")
async def download_report(project_id: int, report_id: int, kind: str, session: SessionDep):
    record = await session.get(ResearchReport, report_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    entry = (record.artifacts or {}).get(kind)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Report {report_id} has no '{kind}' file")
    if not entry.get("path"):
        raise HTTPException(
            status_code=409,
            detail=f"Report {report_id} '{kind}' artifact has no stored location to serve",
        )
    path = Path(entry["path"])
    from ..services.lineage_service import IntegrityError, verify_artifact

    try:
        verify_artifact(path, entry.get("sha256"))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(path, media_type=entry.get("media_type", "application/octet-stream"), filename=path.name)


@router.get("/status", response_model=ScientificStatusOut)
async def scientific_status(project_id: int, session: SessionDep):
    """Prominent, honest split between software validation and scientific validity."""
    await get_project(session, project_id)
    protocols = (
        await session.execute(
            select(EvaluationProtocol).where(EvaluationProtocol.project_id == project_id)
        )
    ).scalars()
    results = (
        await session.execute(
            select(EvaluationResult).where(EvaluationResult.project_id == project_id)
        )
    ).scalars()
    references = (
        await session.execute(
            select(ReferenceArea).where(ReferenceArea.project_id == project_id)
        )
    ).scalars()
    reports = (
        await session.execute(
            select(ResearchReport).where(ResearchReport.project_id == project_id)
        )
    ).scalars()
    disclaimer = research_disclaimer()
    return ScientificStatusOut(
        **disclaimer,
        protocols=len(list(protocols)),
        results=len(list(results)),
        reference_areas=len(list(references)),
        reports=len(list(reports)),
    )
