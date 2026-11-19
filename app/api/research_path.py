"""Portable export of persisted active-learning provenance (not a binary backup)."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Dataset, Label, QueryBatch, Scene, TrainingRun
from ..schemas import ProjectOut, QueryBatchOut, QueryItemOut
from .datasets import dataset_out
from .deps import SessionDep, SettingsDep, get_project
from .labels import _label_out
from .query import _summary
from .scenes import _scene_out
from .training import run_to_summary

router = APIRouter(prefix="/projects/{project_id}", tags=["research-path"])

BATCH_FIELDS = (
    "id", "created_at", "strategy", "method", "strategy_version", "seed", "dataset_id",
    "training_run_id", "model_iteration", "batch_size_requested", "batch_size_returned",
    "samples_added", "decisions",
)
ITEM_FIELDS = (
    "id", "position", "sample_id", "dataset_id", "row", "col", "coords", "geo_coords",
    "score", "uncertainty", "prediction", "confidence", "status", "decided_class",
    "decided_at", "decision_note", "label_id",
)


def csv_cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    # Prevent user-supplied class names and notes becoming spreadsheet formulas.
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


def _center(coordinates):
    center = (coordinates or {}).get("center")
    return tuple(center) if isinstance(center, (list, tuple)) and len(center) == 2 else (None, None)


def sample_ledger(batches, added_ids):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["record_type", *(f"batch_{field}" for field in BATCH_FIELDS),
                     *ITEM_FIELDS, "pixel_center_x", "pixel_center_y", "map_center_x", "map_center_y",
                     "map_crs", "added_sample"])
    for batch in batches:
        prefix = [csv_cell(batch[field]) for field in BATCH_FIELDS]
        for item in batch["items"] or [None]:
            if item is None:
                writer.writerow(["empty_batch", *prefix, *([None] * (len(ITEM_FIELDS) + 6))])
            else:
                writer.writerow(["sample", *prefix, *(csv_cell(item[field]) for field in ITEM_FIELDS),
                                 item["coords"].get("center_x"), item["coords"].get("center_y"), *_center(item["geo_coords"]),
                                 csv_cell((item["geo_coords"] or {}).get("crs")), item["id"] in added_ids])
    return stream.getvalue()


@router.get("/research-path")
async def export_research_path(
    project_id: int, session: SessionDep, settings: SettingsDep,
    format: Literal["json", "csv"] = "json",
) -> Response:
    project = await get_project(session, project_id)

    async def records(model):
        return (await session.scalars(
            select(model).where(model.project_id == project_id).order_by(model.id)
        )).all()

    labels = await records(Label)
    added = [label for label in labels if label.version == 1 and label.query_item_id is not None]
    counts = Counter(label.query_batch_id for label in added)
    batches = (await session.scalars(
        select(QueryBatch).where(QueryBatch.project_id == project_id)
        .options(selectinload(QueryBatch.items)).order_by(QueryBatch.id)
    )).all()
    exported = []
    for batch in batches:
        view = QueryBatchOut(**_summary(batch, counts[batch.id]).model_dump(), items=[
            QueryItemOut.model_validate(item) for item in batch.items
        ]).model_dump(mode="json")
        exported.append(view)

    headers = {
        "Content-Disposition": f'attachment; filename="wbalc-{project_id}-research-path.{format}"',
        "Cache-Control": "no-store",
    }
    if format == "csv":
        return Response(sample_ledger(exported, {label.query_item_id for label in added}),
                        media_type="text/csv", headers=headers)
    return JSONResponse({
        "schema_version": 1,
        "project": ProjectOut.model_validate(project).model_dump(mode="json"),
        "datasets": [dataset_out(row, settings).model_dump(mode="json") for row in await records(Dataset)],
        "scenes": [_scene_out(row, settings).model_dump(mode="json") for row in await records(Scene)],
        "sampling_rounds": exported,
        "label_versions": [_label_out(row).model_dump(mode="json") for row in labels],
        "training_runs": [
            {**run_to_summary(row).model_dump(mode="json"), "manifest": row.manifest}
            for row in await records(TrainingRun)
        ],
        "notes": [
            "A sampling round is a query batch. Training iterations are separate and linked by training_run_id.",
            "samples_added counts retained first label versions attributed to a batch; hard-deleted labels cannot be reconstructed.",
            "Pixel positions are in the source raster grid. geo_coords is null when unavailable and otherwise uses its declared CRS.",
            "Scores and predictions reflect query time, not retraining. Missing values are not inferred.",
        ],
    }, headers=headers)
