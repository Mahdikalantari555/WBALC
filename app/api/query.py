"""Active learning query endpoints (active-learning-query capability)."""

from __future__ import annotations

import anyio
import numpy as np
from fastapi import APIRouter, HTTPException

from fastapi import Query as QueryParam
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..models import Label, QueryBatch, QueryItem, utcnow
from ..schemas import (
    QueryBatchOut,
    QueryBatchSummary,
    QueryDecisionRequest,
    QueryItemOut,
    QueryPoolOut,
    QueryRequest,
    QueryResponse,
    QuerySample,
)
from ..services.al_service import (
    kcenter_greedy,
    select_hybrid,
    select_som,
    select_uncertainty,
    uncertainty_scores,
)
from ..services.query_service import (
    STRATEGY_VERSION,
    describe_pool,
    pixel_query_stride,
    resolve_seed,
    select_random,
)
from ..services.label_service import build_training_targets
from ..services.pipeline import checkpoint_or_409, resolve_inference_contract
from ..services.schema_service import SchemaConflict, classification_band_selection
from ..services.raster_service import (
    RasterError,
    load_raster,
    make_grid,
    patch_features,
    patch_validity,
    pixel_features,
    pixel_to_map,
    sample_id,
)
from ..services.training_service import align_probabilities
from .deps import (
    SessionDep,
    SettingsDep,
    get_project,
    latest_run,
    project_labels,
    require_dataset,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["active-learning"])


@router.post("/query", response_model=QueryResponse)
async def query_batch(
    project_id: int, payload: QueryRequest, session: SessionDep, settings: SettingsDep
):
    """Select the next batch of informative samples to label.

    The candidate pool is a patch grid or a pixel grid — it follows the latest
    checkpoint's resolution unless `sample_resolution` overrides it — and one
    selection rule runs over that pool:

    - uncertainty: requires a model at the pool's granularity; ranks by
      least-confidence, margin or entropy on true per-candidate probabilities.
    - diversity: model-free core-set selection over candidate spectra (works
      for cold start).
    - hybrid: uncertainty pool + core-set diversification; requires a model.
    """
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, payload.dataset_id)

    run = await latest_run(session, project_id)
    needs_model = payload.strategy in ("uncertainty", "hybrid")
    notes: list[str] = []
    checkpoint = None
    if run is not None:
        try:
            checkpoint = checkpoint_or_409(run)
        except HTTPException as exc:
            if needs_model or exc.status_code != 409:
                raise
            checkpoint = None
            notes.append(f"Selected without model scores: {exc.detail}")

    # Pool granularity follows the latest checkpoint's resolution — patch
    # statistics or raw per-pixel spectra — unless the request overrides it.
    # A checkpoint can only score a pool at its own resolution: the mismatch
    # is refused for model-scored strategies instead of misusing the model.
    # Model-free strategies (diversity, random) never score, but their pool
    # still follows the checkpoint so labels stay interchangeable across runs.
    consumes_scores = payload.strategy in ("uncertainty", "hybrid", "som")
    checkpoint_resolution = (
        checkpoint.get("resolution", "patch") if checkpoint is not None else None
    )
    granularity = payload.sample_resolution or checkpoint_resolution or "patch"
    model_checkpoint = None
    if checkpoint is not None:
        if granularity == checkpoint_resolution:
            if consumes_scores:
                try:
                    resolve_inference_contract(run, checkpoint, dataset, accept_unverified=False)
                except HTTPException as exc:
                    if needs_model or exc.status_code != 409:
                        raise
                    notes.append(f"Selected without model scores: {exc.detail}")
                else:
                    model_checkpoint = checkpoint
            else:
                notes.append(
                    f"Strategy '{payload.strategy}' does not use model scores; pool "
                    f"granularity follows the checkpoint ({checkpoint_resolution})."
                )
        elif payload.strategy in ("uncertainty", "hybrid"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Latest model (iteration {run.iteration}) was trained at "
                    f"{checkpoint_resolution} resolution, but a {granularity} pool was "
                    "requested. Query at the checkpoint's resolution, or retrain with "
                    f'{{"resolution": "{granularity}"}} to score {granularity} candidates.'
                ),
            )
        else:
            notes.append(
                f"Latest model (iteration {run.iteration}) was trained at "
                f"{checkpoint_resolution} resolution, so it cannot score a "
                f"{granularity} pool; this batch was selected without model scores."
            )

    if model_checkpoint is None and payload.strategy in ("uncertainty", "hybrid"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Strategy '{payload.strategy}' requires a trained model. "
                "Submit labels and POST /train, or use strategy='diversity' for cold start."
            ),
        )

    try:
        feature_selection = (
            {
                "indices": model_checkpoint["predictor_band_indices"],
                "names": model_checkpoint.get("predictor_band_names") or [],
                "excluded_indices": model_checkpoint.get("excluded_band_indices") or [],
                "excluded_names": model_checkpoint.get("excluded_band_names") or [],
            }
            if model_checkpoint is not None
            else classification_band_selection(dataset.band_schema, dataset.bands)
        )
    except SchemaConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    predictor_band_indices = feature_selection["indices"]

    if granularity == "pixel":
        patch_size, stride = 1, pixel_query_stride(
            dataset.height, dataset.width, payload.stride
        )
    else:
        patch_size = payload.patch_size or (
            model_checkpoint["patch_size"] if model_checkpoint else settings.patch_size
        )
        stride = payload.stride or (
            model_checkpoint["stride"] if model_checkpoint else settings.resolved_stride()
        )

    prediction_classes = list(run.classes) if model_checkpoint is not None else []

    def _compute():
        arr = load_raster(
            dataset.path,
            dataset.nodata,
            settings.max_raster_elements,
            band_indexes=predictor_band_indices,
        )
        grid = make_grid(dataset.height, dataset.width, patch_size, stride)
        if granularity == "pixel":
            # One raw predictor vector per pool pixel: the feature family a
            # pixel-resolution checkpoint was trained on (strict all-band
            # validity, invalid pixels never enter the pool).
            features_all, valid_all = pixel_features(arr)
            selector = np.asarray(
                [y * dataset.width + x for y in grid.ys for x in grid.xs], dtype=np.int64
            )
            X = features_all[selector]
            valid = valid_all[selector]
        else:
            X = patch_features(arr, grid)
            valid = patch_validity(arr, grid)
        probs = None
        if model_checkpoint is not None:
            model = model_checkpoint["model"]
            raw = np.asarray(model.predict_proba(X))
            model_classes = [prediction_classes[int(c)] for c in model.classes_]
            probs = align_probabilities(raw, model_classes, prediction_classes)
        return grid, X, valid, probs

    try:
        grid, X, valid, probs = await anyio.to_thread.run_sync(_compute)
    except RasterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    n_rows, n_cols = grid.shape
    all_sids = [sample_id(dataset.id, r, c) for r in range(n_rows) for c in range(n_cols)]

    # Which patches are already labeled (excluded by default)?
    labels = await project_labels(session, project_id)
    grids = {dataset.id: grid}
    labeled_sids, _, _ = build_training_targets(
        labels, {dataset.id: dataset}, dataset, grids, project.classes
    )
    labeled_set = set(labeled_sids)

    method_used = (
        None
        if payload.strategy == "diversity" or (payload.strategy == "som" and probs is None)
        else payload.method
    )

    # A patch with no valid source pixels has all-zero embeddings and would be
    # ranked as maximally uncertain, so it must never enter the candidate pool.
    # Every strategy samples from this one pool; only `exclude_labeled` changes
    # it, and that choice is recorded on the batch.
    candidate_idx = [
        i
        for i, sid in enumerate(all_sids)
        if valid[i] and not (payload.exclude_labeled and sid in labeled_set)
    ]

    candidate_sids = [all_sids[i] for i in candidate_idx]
    pool = describe_pool(
        candidate_sids,
        patch_size=patch_size,
        stride=stride,
        grid_rows=n_rows,
        grid_cols=n_cols,
        exclude_labeled=payload.exclude_labeled,
        n_labeled_patches=len(labeled_set),
        n_grid_cells=len(all_sids),
    )
    # The granularity is part of the batch's identity: pool.patch_size records
    # it structurally (1 = pixel pool), and the note states it in prose.
    notes.append(
        f"Pool granularity: {granularity} (patch_size {patch_size}, stride {stride}, "
        f"{len(candidate_sids)} candidates)"
    )
    seed = resolve_seed(payload.strategy, payload.seed, settings.random_state)

    if not candidate_idx:
        notes.append("No valid, unlabeled patches remain; upload another dataset or add labels.")
        picked: list[int] = []
    else:
        cand = np.asarray(candidate_idx)
        X_c = X[cand]
        scores = uncertainty_scores(probs[cand], payload.method) if probs is not None else None
        seed_rows = (
            [i for i, sid in enumerate(all_sids) if sid in labeled_set] if labeled_set else []
        )
        seed_idx = np.asarray(seed_rows, dtype=np.int64) if seed_rows else None
        seed_emb = X[seed_idx] if seed_idx is not None else None

        if payload.strategy == "random":
            # Same pool, same size, no model: the baseline active learning is
            # compared against.
            picked = select_random(candidate_sids, payload.batch_size, seed)
        elif payload.strategy == "uncertainty":
            picked = select_uncertainty(scores, payload.batch_size)
        elif payload.strategy == "diversity":
            picked = kcenter_greedy(X_c, payload.batch_size, seed_emb)
        elif payload.strategy == "som":
            try:
                picked = select_som(
                    X_c,
                    payload.batch_size,
                    seed_emb,
                    scores,
                    rows=payload.som_rows,
                    cols=payload.som_cols,
                    epochs=payload.som_epochs,
                    random_state=settings.random_state,
                    target_cell=payload.som_cell,
                    full_embeddings=X,
                    candidate_indices=cand,
                    seed_indices=seed_idx,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        else:  # hybrid
            picked = select_hybrid(
                scores, X_c, payload.batch_size, payload.hybrid_pool_multiplier, seed_emb
            )

    model_scores = None if probs is None else uncertainty_scores(probs, payload.method)
    samples: list[QuerySample] = []
    items: list[QueryItem] = []
    for position, local_i in enumerate(picked):
        i = int(candidate_idx[local_i])
        row, col = divmod(i, n_cols)
        coords = grid.coords(row, col)
        geo = None
        if dataset.transform:
            gx0, gy0 = pixel_to_map(dataset.transform, coords["x0"], coords["y0"])
            gx1, gy1 = pixel_to_map(dataset.transform, coords["x1"], coords["y1"])
            gcx, gcy = pixel_to_map(dataset.transform, coords["center_x"], coords["center_y"])
            geo = {"bbox": [gx0, gy1, gx1, gy0], "center": [gcx, gcy], "crs": dataset.crs}
        prediction = confidence = unc = None
        if probs is not None:
            best = int(np.argmax(probs[i]))
            prediction = prediction_classes[best]
            confidence = float(probs[i, best])
            unc = float(model_scores[i])
        samples.append(
            QuerySample(
                sample_id=all_sids[i],
                dataset_id=dataset.id,
                coords=coords,
                geo_coords=geo,
                prediction=prediction,
                confidence=confidence,
                uncertainty=unc,
                embedding=[float(v) for v in X[i]] if payload.include_embedding else None,
            )
        )
        items.append(
            QueryItem(
                project_id=project_id,
                position=position,
                sample_id=all_sids[i],
                dataset_id=dataset.id,
                row=row,
                col=col,
                coords=coords,
                geo_coords=geo,
                score=float(model_scores[i]) if model_scores is not None else None,
                uncertainty=None if unc is None else float(unc),
                prediction=prediction,
                confidence=confidence,
                status="pending",
            )
        )

    # One transaction: a batch is never visible without its complete item list,
    # and a failing strategy leaves no partial batch behind.
    batch = QueryBatch(
        project_id=project_id,
        dataset_id=dataset.id,
        strategy=payload.strategy,
        method=method_used,
        strategy_version=STRATEGY_VERSION,
        seed=seed,
        batch_size_requested=payload.batch_size,
        batch_size_returned=len(items),
        pool=pool,
        parameters={
            "request": payload.model_dump(exclude_none=True),
            "patch_size": patch_size,
            "stride": stride,
            "exclude_labeled": payload.exclude_labeled,
            "method": method_used,
            "prediction_classes": prediction_classes,
            "predictor_band_indices": predictor_band_indices,
            "predictor_band_names": feature_selection["names"],
            "excluded_band_indices": feature_selection["excluded_indices"],
            "excluded_band_names": feature_selection["excluded_names"],
        },
        model_iteration=run.iteration if model_checkpoint is not None else None,
        training_run_id=run.id if model_checkpoint is not None else None,
        notes=notes,
        note=payload.note,
    )
    batch.items = items
    session.add(batch)
    await session.commit()
    await session.refresh(batch)

    return QueryResponse(
        batch_id=batch.id,
        strategy=payload.strategy,
        method=method_used,
        strategy_version=STRATEGY_VERSION,
        seed=seed,
        batch_size=len(samples),
        requested_size=payload.batch_size,
        model_iteration=batch.model_iteration,
        training_run_id=batch.training_run_id,
        dataset_id=batch.dataset_id,
        created_at=batch.created_at,
        pool=QueryPoolOut(**pool),
        notes=notes,
        samples=samples,
    )


# ------------------------------------------------- durable batch history (Phase 2)
async def _get_batch(session, project_id: int, batch_id: int) -> QueryBatch:
    # Items are always loaded eagerly: the session is closed before the response
    # is serialised, so lazy loading would raise instead of returning a batch.
    result = await session.execute(
        select(QueryBatch)
        .options(selectinload(QueryBatch.items))
        .where(QueryBatch.id == batch_id, QueryBatch.project_id == project_id)
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Query batch {batch_id} not found")
    return batch


def _decision_counts(items: list[QueryItem]) -> dict[str, int]:
    counts = {"pending": 0, "labeled": 0, "rejected": 0, "deferred": 0}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts


async def _added_counts(session, project_id: int, batch_ids: list[int]) -> dict[int, int]:
    if not batch_ids:
        return {}
    from sqlalchemy.orm import aliased

    earlier = aliased(Label)
    first_retained = ~select(earlier.id).where(
        earlier.project_id == Label.project_id, earlier.sample_id == Label.sample_id,
        earlier.version < Label.version, earlier.undone_at.is_(None),
    ).exists()
    rows = await session.execute(
        select(Label.query_batch_id, func.count(Label.id)).where(
            Label.project_id == project_id, first_retained, Label.undone_at.is_(None),
            Label.query_item_id.is_not(None), Label.query_batch_id.in_(batch_ids),
        ).group_by(Label.query_batch_id)
    )
    return {batch_id: count for batch_id, count in rows}


def _summary(batch: QueryBatch, samples_added: int) -> QueryBatchSummary:
    return QueryBatchSummary(
        id=batch.id,
        project_id=batch.project_id,
        dataset_id=batch.dataset_id,
        strategy=batch.strategy,
        method=batch.method,
        strategy_version=batch.strategy_version,
        seed=batch.seed,
        batch_size_requested=batch.batch_size_requested,
        batch_size_returned=batch.batch_size_returned,
        pool=batch.pool,
        parameters=batch.parameters or {},
        model_iteration=batch.model_iteration,
        training_run_id=batch.training_run_id,
        notes=batch.notes or [],
        note=batch.note,
        created_at=batch.created_at,
        decisions=_decision_counts(batch.items),
        samples_added=samples_added,
    )


@router.get("/queries", response_model=list[QueryBatchSummary])
async def list_query_batches(
    project_id: int,
    session: SessionDep,
    limit: int = QueryParam(default=25, ge=1, le=200),
) -> list[QueryBatchSummary]:
    """Durable sampling history, newest first.

    This is project-scoped and identity-free: there is no operator account, so a
    batch records what was selected and why, never who selected it.
    """
    await get_project(session, project_id)
    result = await session.execute(
        select(QueryBatch)
        .options(selectinload(QueryBatch.items))
        .where(QueryBatch.project_id == project_id)
        .order_by(QueryBatch.id.desc())
        .limit(limit)
    )
    batches = result.scalars().unique().all()
    added = await _added_counts(session, project_id, [batch.id for batch in batches])
    return [_summary(batch, added.get(batch.id, 0)) for batch in batches]


@router.get("/queries/{batch_id}", response_model=QueryBatchOut)
async def get_query_batch(project_id: int, batch_id: int, session: SessionDep) -> QueryBatchOut:
    """Reopen a batch from any session: same items, order and decisions."""
    await get_project(session, project_id)
    batch = await _get_batch(session, project_id, batch_id)
    added = await _added_counts(session, project_id, [batch.id])
    summary = _summary(batch, added.get(batch.id, 0))
    return QueryBatchOut(
        **summary.model_dump(),
        items=[QueryItemOut.model_validate(item) for item in batch.items],
    )


@router.patch("/queries/{batch_id}/items/{item_id}", response_model=QueryItemOut)
async def decide_query_item(
    project_id: int,
    batch_id: int,
    item_id: int,
    payload: QueryDecisionRequest,
    session: SessionDep,
) -> QueryItem:
    """Record a durable review decision for one selected sample.

    'labeled' means a label version was submitted for it — either the one named
    by `label_id` or the latest version of that sample. Rejection and deferral are
    decisions in their own right and are kept with their time.
    """
    await get_project(session, project_id)
    batch = await _get_batch(session, project_id, batch_id)
    item = next((entry for entry in batch.items if entry.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Query item {item_id} not in batch {batch_id}")

    if payload.status == "labeled":
        from ..models import Label

        query = select(Label).where(Label.project_id == project_id, Label.sample_id == item.sample_id, Label.undone_at.is_(None))
        if payload.label_id is not None:
            query = query.where(Label.id == payload.label_id)
        result = await session.execute(query.order_by(Label.version.desc()))
        label = result.scalars().first()
        if label is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No label exists for sample {item.sample_id}; submit the label first, "
                    "then record the decision."
                ),
            )
        item.label_id = label.id
        item.decided_class = label.class_name
        # Provenance is written onto the label too, so the association survives
        # independently of this decision row.
        label.query_batch_id = batch.id
        label.query_item_id = item.id
    elif payload.status == "pending":
        item.decided_class = None
        item.label_id = None
    else:
        item.decided_class = payload.class_name

    item.status = payload.status
    item.decision_note = payload.note
    item.decided_at = None if payload.status == "pending" else utcnow()
    await session.commit()
    await session.refresh(item)
    return item
