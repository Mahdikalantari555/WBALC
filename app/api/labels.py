"""Label management endpoints (label-management capability)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from ..models import Label, QueryBatch, QueryItem, utcnow
from ..schemas import LabelBatchCreate, LabelCreate, LabelOut
from ..services.label_service import derive_sample_id, latest_labels
from ..services.pipeline import run_training
from ..services.schema_service import SchemaConflict
from ..services.taxonomy_service import alias_suggestions, resolve_label_class
from ..services.raster_service import make_grid, map_to_pixel
from ..services.training_service import TrainingError
from .deps import (
    SessionDep,
    SettingsDep,
    get_dataset,
    get_project,
    latest_dataset,
    project_labels,
)
from .training import run_to_metrics_out
from ..schemas import TrainResponse

router = APIRouter(prefix="/projects/{project_id}", tags=["labels"])


def _resolve_class_name(project, submitted: str) -> str:
    """Map submitted label text to the project's canonical class name.

    The submitted text is never rewritten in place: the caller stores the
    resolved canonical name on the label while the original request stays in the
    client's history. An alias only exists when the project configured it.
    """
    if submitted in project.classes:
        return submitted
    if project.taxonomy:
        canonical = resolve_label_class(submitted, project.taxonomy)
        if canonical and canonical in project.classes:
            return canonical
        hints = [c for c in alias_suggestions(submitted, project.taxonomy) if c in project.classes]
        detail = (
            f"Label '{submitted}' has no configured mapping in this project's taxonomy "
            f"(version {project.taxonomy.get('version')}). Configure it as an alias of "
            f"one of {project.classes}, or submit one of those names directly."
        )
        if hints:
            detail += f" Closest configured classes: {', '.join(hints)}."
        raise HTTPException(status_code=422, detail=detail)
    raise HTTPException(
        status_code=422,
        detail=f"Unknown class '{submitted}'; project classes: {project.classes}",
    )


async def _store_label(session, settings, project, payload: LabelCreate) -> Label:
    class_name = _resolve_class_name(project, payload.class_name)

    if payload.dataset_id is not None:
        dataset = await get_dataset(session, project.id, payload.dataset_id)
    else:
        dataset = await latest_dataset(session, project.id)

    if payload.coordinate_crs and payload.coordinate_space != "map":
        raise HTTPException(status_code=422, detail="coordinate_crs is only valid with coordinate_space='map'")
    if payload.coordinate_crs and dataset is None:
        raise HTTPException(status_code=422, detail="coordinate_crs conversion requires a selected dataset")
    effective_payload = payload
    if dataset is not None:
        geom = payload.geometry.model_dump()
        if payload.coordinate_space == "map":
            if not dataset.transform:
                raise HTTPException(status_code=422, detail="Map-coordinate labels require a dataset affine transform")
            if payload.coordinate_crs:
                if not dataset.crs:
                    raise HTTPException(status_code=422, detail="CRS conversion requires a georeferenced dataset")
                try:
                    from rasterio.warp import transform as reproject_coordinates
                    if geom["type"] == "Point":
                        xx, yy = reproject_coordinates(payload.coordinate_crs, dataset.crs, [geom["coordinates"][0]], [geom["coordinates"][1]])
                        geom["coordinates"][:2] = [xx[0], yy[0]]
                    else:
                        for ring in geom["coordinates"]:
                            xx, yy = reproject_coordinates(payload.coordinate_crs, dataset.crs, [p[0] for p in ring], [p[1] for p in ring])
                            for position, x, y in zip(ring, xx, yy):
                                position[0], position[1] = x, y
                    effective_payload = payload.model_copy(update={
                        "geometry": payload.geometry.__class__.model_validate(geom),
                        "coordinate_crs": None,
                    })
                except Exception as exc:
                    raise HTTPException(status_code=422, detail=f"Could not transform label coordinates to dataset CRS: {exc}") from exc
            def to_pixel(position):
                return map_to_pixel(dataset.transform, float(position[0]), float(position[1]))
        else:
            def to_pixel(position):
                return float(position[0]), float(position[1])
        if geom["type"] == "Point":
            px, py = to_pixel(geom["coordinates"])
            if not (0 <= px < dataset.width and 0 <= py < dataset.height):
                raise HTTPException(status_code=422, detail="Point label lies outside dataset pixel bounds")
        else:
            pts = [to_pixel(position) for ring in geom["coordinates"] for position in ring]
            xs, ys = zip(*pts)
            if max(xs) <= 0 or max(ys) <= 0 or min(xs) >= dataset.width or min(ys) >= dataset.height:
                raise HTTPException(status_code=422, detail="Polygon label does not overlap dataset pixel bounds")

    grid = (
        make_grid(dataset.height, dataset.width, settings.patch_size, settings.resolved_stride())
        if dataset is not None
        else None
    )
    sid, stype = derive_sample_id(effective_payload, dataset, grid)

    result = await session.execute(
        select(func.max(Label.version)).where(
            Label.project_id == project.id, Label.sample_id == sid
        )
    )
    version = (result.scalar_one_or_none() or 0) + 1

    query_batch_id = None
    query_item_id = None
    if payload.query_item_id is not None or payload.query_batch_id is not None:
        if payload.query_item_id is None:
            raise HTTPException(
                status_code=422,
                detail="query_item_id is required when query_batch_id is given",
            )
        item = await session.get(QueryItem, payload.query_item_id)
        batch = await session.get(QueryBatch, item.batch_id) if item is not None else None
        if item is None or batch is None or batch.project_id != project.id:
            raise HTTPException(
                status_code=422,
                detail=f"Query item {payload.query_item_id} is not part of this project",
            )
        if payload.query_batch_id is not None and payload.query_batch_id != batch.id:
            raise HTTPException(
                status_code=422,
                detail=f"Query item {item.id} belongs to batch {batch.id}, not {payload.query_batch_id}",
            )
        # The link must describe the same sample the label is for, otherwise the
        # provenance would attribute a label to a suggestion it never answered.
        if item.sample_id != sid:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Query item {item.id} is for sample {item.sample_id}, but this label "
                    f"resolves to {sid}"
                ),
            )
        query_batch_id, query_item_id = batch.id, item.id

    label = Label(
        project_id=project.id,
        dataset_id=dataset.id if dataset is not None else None,
        sample_id=sid,
        sample_type=stype,
        geometry=effective_payload.geometry.model_dump(),
        coordinate_space=payload.coordinate_space,
        class_name=class_name,
        submitted_class_name=(
            payload.submitted_class_name
            or (payload.class_name if payload.class_name != class_name else None)
        ),
        iteration=payload.iteration,
        version=version,
        query_batch_id=query_batch_id,
        query_item_id=query_item_id,
    )
    session.add(label)
    if query_item_id is not None:
        # Flush first: the item must reference the real label version id, not a
        # placeholder that a later rollback would leave dangling.
        await session.flush()
        item.label_id = label.id
        item.status = "labeled"
        item.decided_class = class_name
        item.decided_at = utcnow()
        clean = payload.submitted_class_name
        if clean and clean != class_name:
            item.decision_note = f"submitted as '{clean}'"
    return label


def _label_out(label) -> LabelOut:
    """Serialise a label, stating its provenance explicitly.

    `provenance` is derived only from the stored link: a label is 'query' when it
    was submitted from a durable query item, and 'manual' when it was typed or
    imported. It is never guessed from timestamps or matching sample ids.
    """
    out = LabelOut.model_validate(label)
    out.provenance = "query" if label.query_item_id is not None else "manual"
    return out


def _train_response(run) -> TrainResponse:
    return TrainResponse(
        id=run.id,
        project_id=run.project_id,
        iteration=run.iteration,
        model_type=run.model_type,
        checkpoint=run.checkpoint_path,
        n_samples=run.n_samples,
        metrics=run_to_metrics_out(run),
    )


@router.post("/labels", status_code=201)
async def submit_labels(
    project_id: int,
    payload: LabelCreate | LabelBatchCreate,
    session: SessionDep,
    settings: SettingsDep,
    auto_train: bool = Query(default=False, description="Train immediately after storing labels"),
    model_type: str = Query(default="rf", pattern="^(rf|lightgbm)$"),
):
    """Submit one label (object) or a batch ({"labels": [...]}).

    Re-submitting a label for an existing sample_id stores a corrected
    version; full history is preserved. Optionally triggers training on
    the current labeled data (auto_train).
    """
    project = await get_project(session, project_id)

    if isinstance(payload, LabelBatchCreate):
        items = payload.labels
        do_train = payload.auto_train or auto_train
        train_type = payload.model_type if payload.auto_train else model_type
    else:
        items = [payload]
        do_train = auto_train
        train_type = model_type

    stored = [await _store_label(session, settings, project, item) for item in items]
    await session.commit()
    for label in stored:
        await session.refresh(label)

    if isinstance(payload, LabelCreate) and not do_train:
        return _label_out(stored[0])

    result = {
        "labels": [_label_out(l) for l in stored],
        "training": None,
        "training_error": None,
    }
    if do_train:
        try:
            run = await run_training(session, settings, project, model_type=train_type)
            result["training"] = _train_response(run).model_dump()
        except (TrainingError, SchemaConflict) as exc:
            result["training_error"] = str(exc)
    return result


@router.get("/labels", response_model=list[LabelOut])
async def list_current_labels(
    project_id: int,
    session: SessionDep,
    all_versions: bool = Query(default=False),
) -> list[Label]:
    """Current (latest-version) labels; pass all_versions=true for full history."""
    await get_project(session, project_id)
    labels = await project_labels(session, project_id)
    kept = labels if all_versions else latest_labels(labels)
    return [_label_out(label) for label in kept]


@router.get("/history", response_model=list[LabelOut])
async def label_history(project_id: int, session: SessionDep) -> list[Label]:
    """Full label history for the project (all samples, all versions)."""
    await get_project(session, project_id)
    labels = await project_labels(session, project_id)
    return [_label_out(label) for label in labels]


@router.delete("/labels/{sample_id}", status_code=204)
async def delete_sample_labels(project_id: int, sample_id: str, session: SessionDep) -> None:
    """Delete every label version of a sample within the project."""
    await get_project(session, project_id)
    result = await session.execute(
        select(Label).where(Label.project_id == project_id, Label.sample_id == sample_id)
    )
    labels = result.scalars().all()
    if not labels:
        raise HTTPException(status_code=404, detail=f"No labels for sample '{sample_id}'")
    for label in labels:
        await session.delete(label)
    await session.commit()
