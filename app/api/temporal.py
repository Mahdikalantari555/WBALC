"""Scene classification, temporal water mapping and late fusion (Phase 4).

Design rules this router enforces:

- **Native grid first.** A scene is classified on its own grid; nothing is
  resampled unless the caller explicitly asks for alignment to a named
  reference scene, and then the operation and its provenance are recorded.
- **Fail closed on grid mismatch.** Two different grids are never silently
  compared: the response is a structured 409 naming every differing field and
  the resampling option that would fix it.
- **Late fusion only.** Fusion combines *derived* per-analysis probability /
  class products on a declared target grid. Raw-band early fusion is rejected.
- **Areas are quoted with their method** (projected metres vs geographic
  ellipsoid integration) and their valid denominator.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path

import anyio
import numpy as np
import rasterio
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from rasterio.warp import Resampling, reproject
from sqlalchemy import select

from ..models import FusionRun, Scene, SceneAnalysis
from ..schemas import (
    DateAreaPoint,
    FusionRequest,
    FusionResponse,
    SceneAnalysisSummary,
    SceneClassificationRequest,
    SceneClassificationResponse,
    TemporalCompareRequest,
    TemporalCompareResponse,
    TemporalSeriesOut,
)
from ..services.area_service import area_by_class, pixel_areas, transitions, water_areas
from ..services.inference_service import NODATA
from ..services.lineage_service import (
    IntegrityError,
    digest,
    file_identity,
    sha256_file,
    verify_artifact,
)
from ..services.pipeline import checkpoint_or_409
from ..services.scene_service import SceneClassificationError, build_analysis, classify_scene, grid_differences
from ..services.taxonomy_service import BINARY_MAPPINGS
from ..storage import project_dir
from .deps import SessionDep, SettingsDep, get_project, latest_run

router = APIRouter(prefix="/projects/{project_id}", tags=["temporal"])

KIND_ALIASES = {
    "hard": "hard",
    "probability": "probability",
    "uncertainty": "uncertainty",
    "prob": "probability",
    "unc": "uncertainty",
}


# ------------------------------------------------------------------ lookups
async def _get_scene(session, project_id: int, scene_id: int) -> Scene:
    scene = await session.get(Scene, scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(
            status_code=404, detail=f"Scene {scene_id} not found in project {project_id}"
        )
    return scene


async def _get_analysis(session, project_id: int, analysis_id: int) -> SceneAnalysis:
    analysis = await session.get(SceneAnalysis, analysis_id)
    if analysis is None or analysis.project_id != project_id:
        raise HTTPException(
            status_code=404, detail=f"Analysis {analysis_id} not found in project {project_id}"
        )
    return analysis


async def _latest_analysis(session, project_id: int, scene_id: int) -> SceneAnalysis | None:
    result = await session.execute(
        select(SceneAnalysis)
        .where(SceneAnalysis.project_id == project_id, SceneAnalysis.scene_id == scene_id)
        .order_by(SceneAnalysis.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _resolve_analysis(
    session, project_id: int, scene_id: int, analysis_id: int | None
) -> SceneAnalysis:
    """The named analysis, or the newest one for that scene."""
    if analysis_id is not None:
        analysis = await _get_analysis(session, project_id, analysis_id)
        if analysis.scene_id != scene_id:
            raise HTTPException(
                status_code=422,
                detail=f"Analysis {analysis_id} belongs to scene {analysis.scene_id}, not {scene_id}",
            )
        return analysis
    analysis = await _latest_analysis(session, project_id, scene_id)
    if analysis is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Scene {scene_id} has not been classified: POST "
                f"/projects/{project_id}/scenes/{scene_id}/classify first"
            ),
        )
    return analysis


def _analysis_summary(analysis: SceneAnalysis) -> dict:
    return {
        "id": analysis.id,
        "project_id": analysis.project_id,
        "scene_id": analysis.scene_id,
        "training_run_id": analysis.training_run_id,
        "resolution": analysis.resolution,
        "method": analysis.method,
        "classes": list(analysis.classes or []),
        "grid": analysis.grid or {},
        "contract": analysis.contract or {},
        "study_area": analysis.study_area or {},
        "artifacts": analysis.artifacts or {},
        "areas": analysis.areas or {"available": False, "reason": "no area summary recorded"},
        "lineage": analysis.lineage or {},
        "created_at": analysis.created_at,
    }


# ------------------------------------------------------------- artifact I/O
def _artifact_path(analysis: SceneAnalysis, kind: str) -> tuple[Path, dict]:
    entry = (analysis.artifacts or {}).get(kind)
    if not entry or not entry.get("path"):
        raise HTTPException(
            status_code=404, detail=f"Analysis {analysis.id} has no '{kind}' artifact recorded"
        )
    path = Path(entry["path"])
    try:
        result = verify_artifact(path, entry.get("sha256"))
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Analysis {analysis.id} '{kind}' artifact failed its integrity check: {exc} "
                "The record is left untouched; reclassify the scene."
            ),
        ) from exc
    if not result["verified"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Analysis {analysis.id} '{kind}' artifact cannot be verified: "
                f"{result['reason']}"
            ),
        )
    return path, entry


def _validate_export_grid(analysis: SceneAnalysis, path: Path, kind: str) -> dict:
    """Reopen the export and prove it is still on the grid the record claims.

    A checksum proves "the bytes have not changed"; it does not prove the bytes
    describe the recorded grid. Both are checked, because a product written on
    an unexpected grid would silently invalidate every area computed from it.
    """
    grid = _read_grid(path)
    expected = analysis.grid or {}
    problems = grid_differences(
        {"classes": None, **expected}, {**grid, "classes": None}
    )
    if problems:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "export_grid_mismatch",
                "kind": kind,
                "analysis_id": analysis.id,
                "differences": problems,
                "hint": (
                    "The export no longer matches the grid recorded for this analysis. "
                    "Areas from it would be wrong; reclassify the scene."
                ),
            },
        )
    return grid


async def _assert_source_immutable(session, scene: Scene) -> None:
    """The scene file behind an analysis must still be the bytes it was built from."""
    path = Path(scene.storage_path)
    if not path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Scene {scene.id} source file is missing; analyses built from it cannot be reused",
        )
    if not scene.content_sha256:
        return
    actual = await anyio.to_thread.run_sync(lambda: sha256_file(path))
    if actual != scene.content_sha256:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Scene {scene.id} source bytes no longer match its recorded content hash "
                f"(recorded {scene.content_sha256[:12]}…, found {actual[:12]}…); the analysis "
                "record is left untouched but its input is no longer verifiable."
            ),
        )


def _read_grid(path: Path) -> dict:
    with rasterio.open(path) as src:
        return {
            "crs": src.crs.to_string() if src.crs else None,
            "transform": [float(value) for value in list(src.transform)[:6]],
            "width": src.width,
            "height": src.height,
        }


def _load_hard(analysis: SceneAnalysis) -> tuple[np.ndarray, np.ndarray, dict]:
    path, _ = _artifact_path(analysis, "hard")
    _validate_export_grid(analysis, path, "hard")
    with rasterio.open(path) as src:
        data = src.read(1)
        nodata = src.nodata
    valid = np.ones(data.shape, dtype=bool)
    if nodata is not None:
        valid &= data != nodata
    return data, valid, _read_grid(path)


def _load_probability(analysis: SceneAnalysis) -> tuple[np.ndarray, np.ndarray, dict]:
    path, _ = _artifact_path(analysis, "probability")
    _validate_export_grid(analysis, path, "probability")
    with rasterio.open(path) as src:
        data = src.read(out_dtype="float32")
        nodata = src.nodata
    valid = np.isfinite(data).all(axis=0)
    if nodata is not None:
        valid &= ~(data == nodata).any(axis=0)
    return data, valid, _read_grid(path)


def _grid_of(description: dict) -> dict:
    """The comparable subset of a grid description."""
    return {
        "crs": description.get("crs"),
        "transform": [float(value) for value in (description.get("transform") or [])[:6]],
        "width": description.get("width"),
        "height": description.get("height"),
    }


def _same_grid(first: dict, second: dict) -> bool:
    return not grid_differences(
        {**first, "classes": None}, {**second, "classes": None}, tolerance=1e-9
    )


def _reproject(
    array: np.ndarray,
    *,
    source: dict,
    target: dict,
    fill,
    dtype,
    resampling=Resampling.nearest,
) -> np.ndarray:
    """Nearest-neighbour resampling of a (bands, rows, cols) product."""
    stack = array[None, ...] if array.ndim == 2 else array
    out = np.full((stack.shape[0], target["height"], target["width"]), fill, dtype=dtype)
    for band in range(stack.shape[0]):
        reproject(
            source=np.asarray(stack[band], dtype=dtype),
            destination=out[band],
            src_transform=rasterio.Affine(*source["transform"]),
            src_crs=source["crs"],
            dst_transform=rasterio.Affine(*target["transform"]),
            dst_crs=target["crs"],
            src_nodata=fill,
            dst_nodata=fill,
            resampling=resampling,
        )
    return out if array.ndim == 3 else out[0]


def _alignment_record(
    *, source: dict, target: dict, reference_scene_id: int, source_scene_id: int, needed: bool
) -> dict:
    if not needed:
        return {
            "aligned": False,
            "method": "none",
            "reference_scene_id": reference_scene_id,
            "source_scene_id": source_scene_id,
            "note": "source and reference grids are identical; no resampling was performed",
        }
    return {
        "aligned": True,
        "method": "nearest",
        "reference_scene_id": reference_scene_id,
        "source_scene_id": source_scene_id,
        "source_grid": source,
        "target_grid": target,
        "note": (
            "nearest-neighbour resampling onto the reference grid; the native product "
            "is untouched and its own record still describes the original grid"
        ),
    }


def _grid_mismatch_409(first: dict, second: dict, *, reference: dict | None = None) -> HTTPException:
    problems = grid_differences({**first, "classes": None}, {**second, "classes": None})
    return HTTPException(
        status_code=409,
        detail={
            "error": "grid_mismatch",
            "differences": problems,
            "before_grid": first,
            "after_grid": second,
            "reference_scene_id": (reference or {}).get("reference_scene_id"),
            "candidate_scene_id": (reference or {}).get("candidate_scene_id"),
            "resampling_options": ["nearest"],
            "hint": (
                "The two analyses are on different grids and were not compared. Pass "
                "reference_scene_id (one of the two scenes) to request explicit "
                "nearest-neighbour alignment onto that grid, which is recorded in the "
                "response lineage."
            ),
        },
    )


# ------------------------------------------------------- classify one scene
@router.post(
    "/scenes/{scene_id}/classify",
    response_model=SceneClassificationResponse,
    status_code=201,
)
async def classify_scene_endpoint(
    project_id: int,
    scene_id: int,
    payload: SceneClassificationRequest,
    session: SessionDep,
    settings: SettingsDep,
):
    """Classify one scene on its native grid and record an immutable analysis."""
    project = await get_project(session, project_id)
    scene = await _get_scene(session, project_id, scene_id)
    run = await latest_run(session, project_id, payload.iteration)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail="No trained model found; submit labels and POST /train first",
        )
    checkpoint = checkpoint_or_409(run)
    try:
        result = await classify_scene(
            project_id=project_id,
            settings=settings,
            scene=scene,
            run=run,
            checkpoint=checkpoint,
            method=payload.method,
            accept_unverified_schema=payload.accept_unverified_schema,
            study_area_geometry=project.study_area_geometry,
            study_area_crs=project.study_area_crs,
        )
    except SceneClassificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    analysis = build_analysis(
        project_id=project_id, scene=scene, run=run, result=result, method=payload.method
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)

    summary = SceneAnalysisSummary(**_analysis_summary(analysis))
    return SceneClassificationResponse(
        analysis=summary,
        scene_id=scene.id,
        acquisition_datetime=scene.acquisition_datetime,
        sensor=scene.sensor,
    )


@router.get(
    "/scenes/{scene_id}/analyses",
    response_model=list[SceneAnalysisSummary],
)
async def list_scene_analyses(project_id: int, scene_id: int, session: SessionDep):
    await _get_scene(session, project_id, scene_id)
    result = await session.execute(
        select(SceneAnalysis)
        .where(SceneAnalysis.project_id == project_id, SceneAnalysis.scene_id == scene_id)
        .order_by(SceneAnalysis.id)
    )
    return [SceneAnalysisSummary(**_analysis_summary(row)) for row in result.scalars()]


@router.get("/analyses/{analysis_id}", response_model=SceneAnalysisSummary)
async def get_analysis(project_id: int, analysis_id: int, session: SessionDep):
    analysis = await _get_analysis(session, project_id, analysis_id)
    return SceneAnalysisSummary(**_analysis_summary(analysis))


@router.get("/analyses/{analysis_id}/exports/{kind}")
async def download_analysis_export(project_id: int, analysis_id: int, kind: str, session: SessionDep):
    """Stream one scene-classification product, verified before it is sent."""
    analysis = await _get_analysis(session, project_id, analysis_id)
    resolved = KIND_ALIASES.get(kind.lower())
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown export kind '{kind}'; choose one of {sorted(set(KIND_ALIASES.values()))}",
        )
    path, entry = _artifact_path(analysis, resolved)
    _validate_export_grid(analysis, path, resolved)
    scene = await session.get(Scene, analysis.scene_id)
    if scene is not None:
        await _assert_source_immutable(session, scene)
    return FileResponse(
        path,
        media_type="image/tiff",
        filename=path.name,
        headers={
            "X-RSAL-Export-Kind": resolved,
            "X-RSAL-Export-Sha256": entry.get("sha256") or "",
            "X-RSAL-Export-Integrity": "verified",
            "X-RSAL-Analysis-Id": str(analysis.id),
        },
    )


# ------------------------------------------------------- temporal summaries
async def _scene_series(session, project_id: int, scene_ids: list[int] | None) -> list[dict]:
    scenes: list[Scene] = []
    if scene_ids:
        for scene_id in scene_ids:
            scenes.append(await _get_scene(session, project_id, scene_id))
    else:
        result = await session.execute(
            select(Scene).where(Scene.project_id == project_id).order_by(Scene.id)
        )
        scenes = list(result.scalars())

    points: list[dict] = []
    for scene in scenes:
        analysis = await _latest_analysis(session, project_id, scene.id)
        if analysis is None:
            continue
        points.append(
            {
                "scene": scene,
                "analysis": analysis,
                "date": scene.acquisition_datetime or analysis.created_at,
            }
        )
    points.sort(key=lambda entry: (entry["date"], entry["scene"].id))
    return points


def _date_point(entry: dict, classes: list[str]) -> dict:
    scene = entry["scene"]
    analysis = entry["analysis"]
    areas = analysis.areas or {}
    per_class = areas.get("per_class") or []
    if not per_class and classes:
        per_class = [
            {
                "class_index": index,
                "class_name": name,
                "valid_pixels": 0,
                "area_m2": 0.0,
                "area_ha": 0.0,
                "share_of_valid": 0.0,
            }
            for index, name in enumerate(classes)
        ]
    return {
        "scene_id": scene.id,
        "analysis_id": analysis.id,
        "acquisition_datetime": scene.acquisition_datetime,
        "sensor": scene.sensor,
        "valid_area_m2": areas.get("valid_area_m2", 0.0),
        "coverage": areas.get("coverage", 0.0),
        "per_class": per_class,
        "water": areas.get("water"),
        "classes": list(analysis.classes or classes),
        "areas_available": bool(areas.get("available", True)),
    }


@router.get("/temporal/series", response_model=TemporalSeriesOut)
async def temporal_series(
    project_id: int,
    session: SessionDep,
    scene_ids: list[int] | None = Query(default=None),
):
    """Per-date class/water areas from each scene's latest analysis.

    Areas are computed on each scene's *own* grid, so this is a per-date series,
    not a change map: differing grids are reported as caveats rather than
    silently reconciled.
    """
    await get_project(session, project_id)
    entries = await _scene_series(session, project_id, scene_ids)
    if not entries:
        raise HTTPException(
            status_code=409,
            detail=(
                "No scene has been classified yet; POST "
                f"/projects/{project_id}/scenes/{{scene_id}}/classify first"
            ),
        )
    classes = list(entries[-1]["analysis"].classes or [])
    dates = [_date_point(entry, classes) for entry in entries]

    grids = [entry["analysis"].grid or {} for entry in entries]
    mismatched = []
    for index in range(1, len(grids)):
        if not _same_grid(grids[0], grids[index]):
            mismatched.append(entries[index]["scene"].id)
    caveats: list[str] = []
    if len({tuple(entry["analysis"].classes or []) for entry in entries}) > 1:
        caveats.append(
            "Class taxonomies differ between dates; class-wise areas are not directly comparable."
        )
    if mismatched:
        caveats.append(
            "Scenes " + ", ".join(str(sid) for sid in mismatched) + " are on a different grid "
            f"from scene {entries[0]['scene'].id}; per-date areas are computed natively and no "
            "resampling was applied. Use POST /temporal/compare with reference_scene_id for an "
            "explicitly aligned change analysis."
        )
    if any(not date["areas_available"] for date in dates):
        caveats.append(
            "At least one date has no computable pixel-area method; its areas are reported as "
            "unavailable rather than estimated."
        )

    return TemporalSeriesOut(
        project_id=project_id,
        dates=[DateAreaPoint(**{k: v for k, v in date.items() if k != "classes" and k != "areas_available"}) for date in dates],
        classes=classes,
        alignment={
            "mode": "native",
            "resampling": "none",
            "grids_identical": not mismatched,
            "per_date_method": [
                (entry["analysis"].areas or {}).get("method") for entry in entries
            ],
        },
        caveats=caveats,
    )


@router.post("/temporal/compare", response_model=TemporalCompareResponse)
async def temporal_compare(
    project_id: int, payload: TemporalCompareRequest, session: SessionDep
):
    """Class transitions between two dates over their jointly valid footprint."""
    await get_project(session, project_id)
    before_scene = await _get_scene(session, project_id, payload.before_scene_id)
    after_scene = await _get_scene(session, project_id, payload.after_scene_id)
    before = await _resolve_analysis(session, project_id, before_scene.id, None)
    after = await _resolve_analysis(session, project_id, after_scene.id, None)

    if list(before.classes or []) != list(after.classes or []):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "class_taxonomy_mismatch",
                "before_classes": list(before.classes or []),
                "after_classes": list(after.classes or []),
                "hint": "Transition matrices need one class order; retrain on a shared taxonomy.",
            },
        )

    if payload.reference_scene_id is not None and payload.reference_scene_id not in (
        before_scene.id,
        after_scene.id,
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "reference_scene_id must be one of the two compared scenes "
                f"({before_scene.id}, {after_scene.id}); it is only used when their grids differ"
            ),
        )

    before_hard, before_valid, before_grid = _load_hard(before)
    after_hard, after_valid, after_grid = _load_hard(after)

    identical = _same_grid(before_grid, after_grid)
    alignment: dict
    if not identical:
        if payload.reference_scene_id is None:
            raise _grid_mismatch_409(
                before_grid,
                after_grid,
                reference={
                    "reference_scene_id": None,
                    "candidate_scene_id": payload.after_scene_id,
                },
            )
        if payload.reference_scene_id == before_scene.id:
            after_hard = _reproject(
                after_hard.astype(np.int32),
                source=after_grid,
                target=before_grid,
                fill=NODATA,
                dtype=np.int32,
                resampling=Resampling.nearest,
            ).astype(after_hard.dtype)
            after_valid = after_hard != NODATA
            target = before_grid
            source_grid, source_scene = after_grid, after_scene.id
        else:
            before_hard = _reproject(
                before_hard.astype(np.int32),
                source=before_grid,
                target=after_grid,
                fill=NODATA,
                dtype=np.int32,
                resampling=Resampling.nearest,
            ).astype(before_hard.dtype)
            before_valid = before_hard != NODATA
            target = after_grid
            source_grid, source_scene = before_grid, before_scene.id
        alignment = _alignment_record(
            source=source_grid,
            target=target,
            reference_scene_id=payload.reference_scene_id,
            source_scene_id=source_scene,
            needed=True,
        )
        reference_grid = target
    else:
        alignment = _alignment_record(
            source=before_grid,
            target=after_grid,
            reference_scene_id=payload.reference_scene_id or before_scene.id,
            source_scene_id=after_scene.id,
            needed=False,
        )
        reference_grid = before_grid

    classes = list(before.classes or [])
    # Area weights come from the reference grid's own geometry, so an aligned
    # change map is measured in the reference scene's real pixel areas.
    try:
        rows, method_info = pixel_areas(
            rasterio.crs.CRS.from_user_input(reference_grid["crs"]),
            reference_grid["transform"],
            reference_grid["height"],
            reference_grid["width"],
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Pixel areas are not computable: {exc}") from exc

    try:
        matrix = transitions(
            before_hard, after_hard, before_valid, after_valid, classes, rows, nodata=int(NODATA)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    before_areas = area_by_class(before_hard, before_valid, classes, rows, nodata=int(NODATA))
    after_areas = area_by_class(after_hard, after_valid, classes, rows, nodata=int(NODATA))
    before_areas["method"] = method_info
    after_areas["method"] = method_info
    interpretation = (before.taxonomy or {}).get("binary_interpretation")
    if interpretation in BINARY_MAPPINGS:
        water = list(BINARY_MAPPINGS[interpretation]["water"])
        before_areas["water"] = water_areas(before_areas, water)
        after_areas["water"] = water_areas(after_areas, water)

    caveats: list[str] = []
    if alignment["aligned"]:
        caveats.append(
            "Changes are measured after nearest-neighbour alignment onto scene "
            f"{payload.reference_scene_id}'s grid; resampling can shift class boundaries by up "
            "to one source pixel."
        )
    if matrix["joint_valid_pixels"] == 0:
        caveats.append("The two dates share no jointly valid pixels; nothing was compared.")
    caveats.append(
        "Only pixels valid in both dates are counted, so a change in cloud/validity cover "
        "cannot appear as a land-cover change."
    )

    lineage = {
        "before_analysis_id": before.id,
        "after_analysis_id": after.id,
        "before_scene_id": before_scene.id,
        "after_scene_id": after_scene.id,
        "before_analysis_digest": (before.lineage or {}).get("analysis_digest"),
        "after_analysis_digest": (after.lineage or {}).get("analysis_digest"),
        "alignment": alignment,
        "area_method": method_info,
        "classes": classes,
    }
    lineage["comparison_digest"] = digest(lineage)

    return TemporalCompareResponse(
        before_scene_id=before_scene.id,
        after_scene_id=after_scene.id,
        classes=classes,
        alignment=alignment,
        transitions={
            "classes": matrix["classes"],
            "matrix": matrix["matrix"],
            "matrix_area_m2": matrix["matrix_area_m2"],
            "joint_valid_pixels": matrix["joint_valid_pixels"],
            "joint_valid_area_m2": matrix["joint_valid_area_m2"],
            "joint_valid_area_ha": matrix["joint_valid_area_ha"],
            "changed_pixels": matrix["changed_pixels"],
            "changed_area_m2": matrix["changed_area_m2"],
            "changed_area_ha": matrix["changed_area_ha"],
            "unchanged_pixels": matrix["unchanged_pixels"],
            "changes": matrix["changes"],
            "denominator": matrix["denominator"],
        },
        before=DateAreaPoint(
            **_date_point({"scene": before_scene, "analysis": before, "date": None}, classes)
            | {"per_class": before_areas["per_class"], "water": before_areas.get("water"),
               "valid_area_m2": before_areas["valid_area_m2"],
               "coverage": before_areas["coverage"]}
        ),
        after=DateAreaPoint(
            **_date_point({"scene": after_scene, "analysis": after, "date": None}, classes)
            | {"per_class": after_areas["per_class"], "water": after_areas.get("water"),
               "valid_area_m2": after_areas["valid_area_m2"],
               "coverage": after_areas["coverage"]}
        ),
        lineage=lineage,
        caveats=caveats,
    )


# ------------------------------------------------------------------- fusion
@router.post("/fusion", response_model=FusionResponse, status_code=201)
async def create_fusion(
    project_id: int, payload: FusionRequest, session: SessionDep, settings: SettingsDep
):
    """Late fusion of derived per-analysis products on a declared target grid."""
    await get_project(session, project_id)
    if payload.rule in ("early_fusion", "raw_band_fusion"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "early_fusion_rejected",
                "detail": (
                    "This engine only fuses *derived* per-scene products (late fusion) on a "
                    "declared target grid. Combining raw bands across sensors would need a "
                    "harmonisation step this engine does not implement, and the result could "
                    "not be decomposed back into per-sensor evidence."
                ),
                "supported_rules": ["weighted_probability", "weighted_vote", "priority"],
            },
        )
    if len(payload.analysis_ids) < 2:
        raise HTTPException(
            status_code=422, detail="analysis_ids must list at least two analyses to fuse"
        )

    target_scene = await _get_scene(session, project_id, payload.target_scene_id)
    analyses = [await _get_analysis(session, project_id, aid) for aid in payload.analysis_ids]
    if len({a.id for a in analyses}) != len(analyses):
        raise HTTPException(status_code=422, detail="analysis_ids contains duplicates")

    class_lists = {tuple(a.classes or []) for a in analyses}
    if len(class_lists) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "class_taxonomy_mismatch",
                "class_orders": [list(entry) for entry in class_lists],
                "hint": "Late fusion needs a shared class order across sources.",
            },
        )
    classes = list(analyses[0].classes or [])

    # The target grid is a real scene's grid: an explicit, checkable artefact.
    target_grid = _grid_of(
        {
            "crs": target_scene.crs,
            "transform": [float(v) for v in (target_scene.transform or [])[:6]],
            "width": target_scene.width,
            "height": target_scene.height,
        }
    )
    if not target_grid["crs"] or not target_grid["transform"]:
        raise HTTPException(
            status_code=422, detail=f"Target scene {target_scene.id} has no CRS/affine"
        )

    sources = []
    stacks: list[np.ndarray] = []
    validities: list[np.ndarray] = []
    for analysis in analyses:
        scene = await _get_scene(session, project_id, analysis.scene_id)
        prob, valid, grid = _load_probability(analysis)
        aligned = not _same_grid(grid, target_grid)
        if aligned:
            # Probability GeoTIFFs use PROBABILITY_NODATA (-9999), while the
            # categorical reproject helper is given the hard-map sentinel. Map
            # invalid source cells to that fill before warping, then exclude it
            # explicitly: finite nodata sentinels are not valid probabilities.
            prob = np.where(valid[None, :, :], prob, NODATA).astype(np.float32, copy=False)
            prob = _reproject(
                prob,
                source=grid,
                target=target_grid,
                fill=NODATA,
                dtype=np.float32,
                resampling=Resampling.nearest,
            )
            valid = np.isfinite(prob).all(axis=0) & ~(prob == NODATA).any(axis=0)
        sensor = scene.sensor
        weight = float(payload.weights.get(sensor, payload.weights.get(str(analysis.id), 1.0)))
        if not math.isfinite(weight) or weight < 0:
            raise HTTPException(
                status_code=422, detail=f"Weight for {sensor} must be finite and non-negative ({weight})"
            )
        sources.append(
            {
                "analysis_id": analysis.id,
                "scene_id": analysis.scene_id,
                "sensor": sensor,
                "weight": weight,
                "grid_aligned": aligned,
                "analysis_digest": (analysis.lineage or {}).get("analysis_digest"),
                "grid": grid,
            }
        )
        stacks.append(prob)
        validities.append(valid)

    stacked = np.stack(stacks, axis=0)  # (sources, classes, rows, cols)
    stack_valid = np.stack(validities, axis=0)  # (sources, rows, cols)
    rows, cols = target_grid["height"], target_grid["width"]
    shape = (len(classes), rows, cols)
    weighted_rule = payload.rule in ("weighted_probability", "weighted_vote")
    participating_indices = (
        [index for index, entry in enumerate(sources) if entry["weight"] > 0]
        if weighted_rule
        else list(range(len(sources)))
    )
    if weighted_rule and not participating_indices:
        raise HTTPException(status_code=422, detail="At least one source weight must be positive")
    weight_scale = (
        max(sources[index]["weight"] for index in participating_indices)
        if weighted_rule
        else 1.0
    )
    normalized_weights = (
        {index: sources[index]["weight"] / weight_scale for index in participating_indices}
        if weighted_rule
        else {}
    )

    if payload.rule == "weighted_probability":
        fused = np.zeros(shape, dtype=np.float32)
        weight_sum = np.zeros((rows, cols), dtype=np.float32)
        for index in participating_indices:
            weight = np.float32(normalized_weights[index])
            valid_source = stack_valid[index]
            contribution = np.where(valid_source[None, :, :], stacked[index], 0.0)
            fused += weight * contribution
            weight_sum += weight * valid_source
        keep = (
            stack_valid.all(axis=0)
            if payload.missing_policy == "require_all"
            else stack_valid[participating_indices].any(axis=0)
        )
        keep &= weight_sum > 0
        fused = np.divide(fused, weight_sum, out=np.zeros(shape, dtype=np.float32), where=weight_sum > 0)
        fused[:, ~keep] = np.nan
        missing_note = (
            "a pixel is fused only where every source is valid; elsewhere the result is nodata"
            if payload.missing_policy == "require_all"
            else "weights are renormalised over valid positive-weight sources at each pixel"
        )
    elif payload.rule == "weighted_vote":
        # Each positive-weight source casts one weighted vote for its own hard class.
        fused = np.zeros(shape, dtype=np.float32)
        for index in participating_indices:
            weight = np.float32(normalized_weights[index])
            hard_source = np.argmax(
                np.where(stack_valid[index][None, :, :], stacked[index], -1.0), axis=0
            )
            hard_source = np.where(stack_valid[index], hard_source, -1)
            for class_index in range(len(classes)):
                fused[class_index] += weight * (hard_source == class_index)
        keep = (
            stack_valid.all(axis=0)
            if payload.missing_policy == "require_all"
            else stack_valid[participating_indices].any(axis=0)
        )
        keep &= np.any(fused > 0, axis=0)
        fused[:, ~keep] = np.nan
        missing_note = (
            "each positive-weight source casts one weighted vote; every source must be valid "
            "and ties break toward the lower class index"
            if payload.missing_policy == "require_all"
            else "each valid positive-weight source casts one weighted vote; ties break toward the lower class index"
        )
    elif payload.rule == "priority":
        order = payload.priority or [entry["analysis_id"] for entry in sources]
        if set(order) != {entry["analysis_id"] for entry in sources} or len(order) != len(sources):
            raise HTTPException(
                status_code=422,
                detail="priority must list every analysis_id exactly once",
            )
        fused = np.full(shape, np.nan, dtype=np.float32)
        decided = np.zeros((rows, cols), dtype=bool)
        for analysis_id in order:
            index = [entry["analysis_id"] for entry in sources].index(analysis_id)
            take = stack_valid[index] & ~decided
            fused[:, take] = stacked[index][:, take]
            decided |= take
        if payload.missing_policy == "require_all":
            joint = stack_valid.all(axis=0)
            fused[:, ~joint] = np.nan
            missing_note = (
                "every source must be valid; among them the first source in priority order decides, "
                "otherwise the result is nodata"
            )
        else:
            missing_note = "the first valid source in priority order decides each pixel"

    fused = fused.astype(np.float32, copy=False)
    fused_hard = np.argmax(fused, axis=0).astype(np.int32)
    any_valid = np.isfinite(fused).any(axis=0)
    fused_hard[~any_valid] = NODATA

    # Agreement counts only sources that participate in this rule: positive
    # weights for weighted rules, every source for priority.
    votes = np.zeros((rows, cols), dtype=np.int32)
    hard_per_source: dict[int, np.ndarray] = {}
    for index in participating_indices:
        hard_source = np.argmax(
            np.where(stack_valid[index][None, :, :], stacked[index], -1.0), axis=0
        )
        hard_per_source[index] = np.where(stack_valid[index], hard_source, -1)
        votes += (hard_per_source[index] == fused_hard) & any_valid
    agreement_count = len(participating_indices)
    unanimous = (votes == agreement_count) & any_valid
    agreement = {
        "sources": agreement_count,
        "unanimous_pixels": int(unanimous.sum()),
        "fused_valid_pixels": int(any_valid.sum()),
        "unanimous_share": float(unanimous.sum()) / float(any_valid.sum()) if any_valid.sum() else 0.0,
        "mean_agreeing_sources": float(votes[any_valid].mean()) if any_valid.sum() else 0.0,
        "per_source": [
            {
                "analysis_id": entry["analysis_id"],
                "sensor": entry["sensor"],
                "participates": index in hard_per_source,
                "agreeing_pixels": int(((hard_per_source[index] == fused_hard) & any_valid).sum())
                if index in hard_per_source else 0,
            }
            for index, entry in enumerate(sources)
        ],
    }

    try:
        rows_area, area_method = pixel_areas(
            rasterio.crs.CRS.from_user_input(target_grid["crs"]),
            target_grid["transform"],
            rows,
            cols,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Pixel areas are not computable: {exc}") from exc
    areas = area_by_class(fused_hard, any_valid, classes, rows_area, nodata=int(NODATA))
    areas["method"] = area_method
    taxonomy = {}
    for analysis in analyses:
        if analysis.taxonomy:
            taxonomy = analysis.taxonomy
            break
    interpretation = taxonomy.get("binary_interpretation")
    if interpretation in BINARY_MAPPINGS:
        areas["water"] = water_areas(areas, list(BINARY_MAPPINGS[interpretation]["water"]))

    # Write the fused hard map on the declared target grid.
    export_dir = project_dir(settings, "exports", project_id)
    tag = f"fusion_{uuid.uuid4().hex[:8]}"
    path = export_dir / f"fused_hard_{tag}.tif"
    _write_fused_geotiff(path, fused_hard, classes, target_grid, {
        "rule": payload.rule,
        "sources": [entry["analysis_id"] for entry in sources],
    })
    identity = file_identity(path)

    lineage = {
        "rule": payload.rule,
        "weights": {entry["sensor"]: entry["weight"] for entry in sources},
        "target_grid": target_grid,
        "sources": [
            {
                "analysis_id": entry["analysis_id"],
                "scene_id": entry["scene_id"],
                "sensor": entry["sensor"],
                "weight": entry["weight"],
                "grid_aligned": entry["grid_aligned"],
                "analysis_digest": entry["analysis_digest"],
            }
            for entry in sources
        ],
        "missing_policy": payload.missing_policy,
        "missing_semantics": missing_note,
        "classes": classes,
        "fusion_kind": "late",
        "fused_sha256": (identity or {}).get("sha256"),
    }
    lineage["fusion_digest"] = digest(lineage)

    record = FusionRun(
        project_id=project_id,
        name=payload.name or f"fusion {len(sources)} sources",
        rule=payload.rule,
        weights=lineage["weights"],
        target_grid=target_grid,
        source_analysis_ids=[entry["analysis_id"] for entry in sources],
        missing_policy=payload.missing_policy,
        alignment={
            "resampling": "nearest" if any(entry["grid_aligned"] for entry in sources) else "none",
            "aligned_sources": [e["analysis_id"] for e in sources if e["grid_aligned"]],
            "note": missing_note,
        },
        classes=classes,
        hard=None,
        areas=areas,
        agreement=agreement,
        lineage={**lineage, "artifact": {"path": str(path), "name": path.name, **(identity or {})}},
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return FusionResponse(
        id=record.id,
        project_id=project_id,
        name=record.name,
        rule=record.rule,
        weights=record.weights,
        target_grid=record.target_grid,
        alignment=record.alignment,
        missing_policy=record.missing_policy,
        sources=[{k: v for k, v in entry.items() if k != "grid"} for entry in sources],
        classes=classes,
        areas=areas,
        agreement=agreement,
        artifacts={"hard": record.lineage["artifact"]},
        lineage=record.lineage,
        created_at=record.created_at,
    )


def _write_fused_geotiff(path: Path, hard: np.ndarray, classes: list[str], grid: dict, meta: dict) -> None:
    import json

    from ..services.inference_service import _atomic_write, class_colors

    data = hard.astype(np.uint16)

    def _write(tmp: Path) -> None:
        with rasterio.open(
            tmp,
            "w",
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype="uint16",
            crs=grid["crs"],
            transform=rasterio.Affine(*grid["transform"]),
            nodata=int(NODATA),
            compress="deflate",
        ) as dst:
            dst.write(data, 1)
            dst.update_tags(classes=json.dumps(classes), **{k: str(v) for k, v in meta.items()})
            dst.write_colormap(
                1,
                {index: (*class_colors(len(classes))[index], 255) for index in range(len(classes))},
            )

    _atomic_write(path, _write)


@router.get("/fusion", response_model=list[FusionResponse])
async def list_fusions(project_id: int, session: SessionDep):
    await get_project(session, project_id)
    result = await session.execute(
        select(FusionRun).where(FusionRun.project_id == project_id).order_by(FusionRun.id)
    )
    return [_fusion_payload(row) for row in result.scalars()]


@router.get("/fusion/{fusion_id}", response_model=FusionResponse)
async def get_fusion(project_id: int, fusion_id: int, session: SessionDep):
    record = await session.get(FusionRun, fusion_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Fusion {fusion_id} not found in project {project_id}")
    return _fusion_payload(record)


def _fusion_payload(record: FusionRun) -> dict:
    lineage = record.lineage or {}
    sources = lineage.get("sources") or []
    return {
        "id": record.id,
        "project_id": record.project_id,
        "name": record.name,
        "rule": record.rule,
        "weights": record.weights or {},
        "target_grid": record.target_grid or {},
        "alignment": record.alignment or {},
        "missing_policy": record.missing_policy,
        "sources": sources,
        "classes": list(record.classes or []),
        "areas": record.areas or None,
        "agreement": record.agreement or {},
        "artifacts": {"hard": lineage.get("artifact")} if lineage.get("artifact") else {},
        "lineage": lineage,
        "created_at": record.created_at,
    }
