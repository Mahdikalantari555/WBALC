"""Active learning query endpoints (active-learning-query capability)."""

from __future__ import annotations

import anyio
import numpy as np
from fastapi import APIRouter, HTTPException

from ..schemas import QueryRequest, QueryResponse, QuerySample
from ..services.al_service import (
    kcenter_greedy,
    select_hybrid,
    select_som,
    select_uncertainty,
    uncertainty_scores,
)
from ..services.label_service import build_training_targets
from ..services.pipeline import checkpoint_or_409
from ..services.raster_service import (
    RasterError,
    load_raster,
    make_grid,
    patch_features,
    patch_validity,
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
    """Select the next batch of informative patches to label.

    - uncertainty: requires a trained model; ranks by least-confidence,
      margin or entropy.
    - diversity: model-free core-set selection over patch embeddings
      (works for cold start).
    - hybrid: uncertainty pool + core-set diversification; requires a model.
    """
    project = await get_project(session, project_id)
    dataset = await require_dataset(session, project_id, payload.dataset_id)

    run = await latest_run(session, project_id)
    checkpoint = checkpoint_or_409(run) if run is not None else None
    notes: list[str] = []

    if checkpoint is not None and checkpoint["bands"] != dataset.bands:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Model expects {checkpoint['bands']} bands but dataset {dataset.id} "
                f"has {dataset.bands}; train on this dataset first"
            ),
        )

    # Queries are patch-grid operations: embeddings are per-band patch
    # statistics, so only a patch-feature checkpoint can score them. A pixel
    # checkpoint would otherwise reach predict_proba with the wrong width and
    # surface as an opaque 500.
    model_checkpoint = checkpoint
    if checkpoint is not None and checkpoint.get("resolution") != "patch":
        if payload.strategy in ("uncertainty", "hybrid"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Latest model (iteration {run.iteration}) was trained at "
                    f"{checkpoint.get('resolution')} resolution, but active-learning "
                    "queries rank patch embeddings. Retrain with "
                    '{"resolution": "patch"} to query with model scores, or use '
                    "strategy='diversity'/'som' which do not need a model."
                ),
            )
        model_checkpoint = None
        notes.append(
            f"Latest model (iteration {run.iteration}) was trained at "
            f"{checkpoint.get('resolution')} resolution, so it cannot score patch "
            "embeddings; this batch was selected without model scores."
        )

    if model_checkpoint is None and payload.strategy in ("uncertainty", "hybrid"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Strategy '{payload.strategy}' requires a trained model. "
                "Submit labels and POST /train, or use strategy='diversity' for cold start."
            ),
        )

    patch_size = payload.patch_size or (
        model_checkpoint["patch_size"] if model_checkpoint else settings.patch_size
    )
    stride = payload.stride or (
        model_checkpoint["stride"] if model_checkpoint else settings.resolved_stride()
    )

    def _compute():
        arr = load_raster(dataset.path, dataset.nodata, settings.max_raster_elements)
        grid = make_grid(dataset.height, dataset.width, patch_size, stride)
        X = patch_features(arr, grid)
        valid = patch_validity(arr, grid)
        probs = None
        if model_checkpoint is not None:
            model = model_checkpoint["model"]
            raw = np.asarray(model.predict_proba(X))
            model_classes = [project.classes[int(c)] for c in model.classes_]
            probs = align_probabilities(raw, model_classes, project.classes)
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
    candidate_idx = [
        i
        for i, sid in enumerate(all_sids)
        if valid[i] and not (payload.exclude_labeled and sid in labeled_set)
    ]
    if not candidate_idx:
        return QueryResponse(
            strategy=payload.strategy,
            method=method_used,
            batch_size=0,
            model_iteration=run.iteration if model_checkpoint is not None else None,
            notes=notes
            + ["No valid, unlabeled patches remain; upload another dataset or add labels."],
            samples=[],
        )

    cand = np.asarray(candidate_idx)
    X_c = X[cand]
    scores = uncertainty_scores(probs[cand], payload.method) if probs is not None else None
    seed_rows = [i for i, sid in enumerate(all_sids) if sid in labeled_set] if labeled_set else []
    seed_idx = np.asarray(seed_rows, dtype=np.int64) if seed_rows else None
    seed = X[seed_idx] if seed_idx is not None else None

    if payload.strategy == "uncertainty":
        picked = select_uncertainty(scores, payload.batch_size)
    elif payload.strategy == "diversity":
        picked = kcenter_greedy(X_c, payload.batch_size, seed)
    elif payload.strategy == "som":
        try:
            picked = select_som(
                X_c,
                payload.batch_size,
                seed,
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
        picked = select_hybrid(scores, X_c, payload.batch_size, payload.hybrid_pool_multiplier, seed)

    samples: list[QuerySample] = []
    for local_i in picked:
        i = int(cand[local_i])
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
            prediction = project.classes[best]
            confidence = float(probs[i, best])
            unc = float(uncertainty_scores(probs[i : i + 1], payload.method)[0])
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

    return QueryResponse(
        strategy=payload.strategy,
        method=method_used,
        batch_size=len(samples),
        model_iteration=run.iteration if model_checkpoint is not None else None,
        notes=notes,
        samples=samples,
    )
