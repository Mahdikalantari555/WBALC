"""Per-Scene classification on the Scene's own grid (Phase 4).

A `Scene` is not a `Dataset`: it carries its own CRS, affine, band list and
sensor. This module therefore never assumes two scenes agree. It

1. proves the model's declared band schema matches *this* scene's declared band
   names/polarizations, and refuses when it cannot (a Sentinel-1 GRD and a
   Sentinel-2 L2A can have the same band count and mean nothing alike);
2. applies the project study area with an explicit, recorded inclusion rule;
3. classifies on the scene's native grid and writes hard / probability /
   uncertainty GeoTIFFs on that exact grid;
4. computes areas from the grid's affine and CRS units;
5. returns an immutable `SceneAnalysis` record so the question "which model,
   which bands, which mask, which grid?" is answered from the record.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio
import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS

from ..config import Settings
from ..models import Scene, SceneAnalysis, TrainingRun, utcnow
from ..storage import project_dir
from .area_service import area_by_class, pixel_areas, water_areas
from .inference_service import (
    _atomic_write,
    export_hard_cells_geotiff,
    export_probability_cells_geotiff,
    grid_metadata,
    maps_from_inference,
    pixel_transform,
    export_uncertainty_geotiff,
    export_uncertainty_cells_geotiff,
)
from .lineage_service import digest, file_identity
from .mask_service import StudyAreaError, study_area_mask
from .raster_service import RasterError, check_element_budget, make_grid, patch_features, patch_validity, pixel_features
from .schema_service import build_band_schema, compare_schemas
from .taxonomy_service import BINARY_MAPPINGS
from .training_service import align_probabilities

# Cell grids below this many cells are written cell-by-cell; the painting
# helpers already stream, so the limit only guards pathological inputs.
_MAX_SCENE_CELLS = 250_000


class SceneClassificationError(ValueError):
    """A request the engine refuses rather than guessing its way through."""


def scene_band_schema(scene: Scene) -> dict:
    """The scene's ordered band identity, as declared by its own metadata.

    Priority: per-band descriptions/names written by the product, then the
    polarization list *only when its length matches the band count* (so a
    two-polarization product cannot be used to name a four-band stack). With
    neither, the schema is explicitly undeclared rather than invented.
    """
    names = [str(desc) for desc in (scene.band_descriptions or []) if desc]
    if not names or len(names) != scene.band_count:
        names = [str(name) for name in (scene.band_names or []) if name]
    if len(names) != scene.band_count:
        names = []
    source = "scene-band-descriptions" if names else None
    if not names and scene.polarization and len(scene.polarization) == scene.band_count:
        names = [str(pol) for pol in scene.polarization]
        source = "scene-polarization"
    schema = build_band_schema(
        band_count=scene.band_count,
        band_names=names or None,
        sensor=scene.sensor,
        source=source or "scene-raster-metadata",
    )
    return {**schema, "scene_id": scene.id}


def scene_grid(scene: Scene) -> dict:
    """Everything needed to prove two results share (or do not share) a grid."""
    return {
        "scene_id": scene.id,
        "crs": scene.crs,
        "transform": [float(value) for value in scene.transform] if scene.transform else None,
        "width": scene.width,
        "height": scene.height,
        "band_count": scene.band_count,
        "sensor": scene.sensor,
        "has_validity_mask": scene.has_validity_mask,
        "mask_flags": scene.mask_flags,
        "nodata_values": scene.nodata_values,
    }


def grid_differences(
    first: dict, second: dict, *, tolerance: float = 1e-9
) -> list[dict]:
    """Every field that makes two grids incompatible, empty when identical.

    Returned as data (not just a message) so an API can hand a client a
    structured 409 it can act on.
    """
    problems: list[dict] = []
    for field in ("crs", "width", "height"):
        if first.get(field) != second.get(field):
            problems.append(
                {"field": field, "reference": first.get(field), "candidate": second.get(field)}
            )
    left, right = first.get("transform"), second.get("transform")
    if left is None or right is None:
        if left != right:
            problems.append({"field": "transform", "reference": left, "candidate": right})
    else:
        for index, (a, b) in enumerate(zip(left, right)):
            if abs(float(a) - float(b)) > tolerance:
                problems.append(
                    {
                        "field": f"transform[{index}]",
                        "reference": float(a),
                        "candidate": float(b),
                    }
                )
    if first.get("classes") and second.get("classes") and first["classes"] != second["classes"]:
        problems.append(
            {
                "field": "classes",
                "reference": first["classes"],
                "candidate": second["classes"],
            }
        )
    return problems


def assert_same_grid(first: dict, second: dict) -> None:
    problems = grid_differences(first, second)
    if problems:
        raise SceneClassificationError(
            "Analyses are not on the same grid, so they are not directly comparable: "
            + "; ".join(f"{p['field']} {p['reference']} vs {p['candidate']}" for p in problems)
        )


def require_compatible_model(
    run: TrainingRun, checkpoint: dict, scene: Scene, *, accept_unverified: bool = False
) -> dict:
    """Refuse a model whose declared bands do not match this scene's.

    `accept_unverified` is an explicit, recorded override — never a default. A
    band-count match is not evidence of meaning.
    """
    if checkpoint["bands"] != scene.band_count:
        raise SceneClassificationError(
            f"Model expects {checkpoint['bands']} bands but scene {scene.id} "
            f"({scene.sensor}) has {scene.band_count}"
        )
    expected = checkpoint.get("band_schema") or (run.params or {}).get("band_schema")
    actual = scene_band_schema(scene)
    if not actual["declared"]:
        raise SceneClassificationError(
            f"Scene {scene.id} declares no band names or polarizations, so its band "
            "identity cannot be proven equal to the model's. Classification is refused "
            "rather than assumed from a matching band count."
        )
    verified, reason = compare_schemas(expected, actual)
    if not verified and not accept_unverified:
        raise SceneClassificationError(
            f"Scene {scene.id} band schema cannot be proven compatible with the model: "
            f"{reason}. Repeat with accept_unverified_schema=true to record an explicit "
            "override."
        )
    return {
        "verified": verified,
        "reason": reason,
        "override": bool(accept_unverified and not verified),
        "scene_schema": actual,
    }


def _read_scene(scene: Scene, settings: Settings) -> tuple[np.ndarray, np.ndarray]:
    path = Path(scene.storage_path)
    if not path.exists():
        raise SceneClassificationError(f"Scene {scene.id} file is missing from storage")
    check_element_budget(
        scene.band_count,
        scene.height,
        scene.width,
        settings.max_raster_elements,
        what="scene classification",
    )
    with rasterio.open(path) as src:
        data = src.read(masked=True, out_dtype="float32")
    filled = data.filled(np.nan)
    valid = np.isfinite(filled).all(axis=0)
    if getattr(data, "mask", None) is not None:
        valid &= ~np.asarray(data.mask).any(axis=0)
    return filled, valid


def _cell_pixel_area(grid, row_areas: np.ndarray, height: int, width: int) -> np.ndarray:
    """Sum the covered pixels' areas into each cell (cells are flat rectangles)."""
    areas = np.zeros(grid.shape, dtype=np.float64)
    flat = np.asarray(row_areas, dtype=np.float64).reshape(-1)
    for row in range(grid.shape[0]):
        y0 = min(grid.ys[row], height)
        y1 = min(y0 + grid.patch_h, height)
        rows_total = float(flat[y0:y1].sum()) if y1 > y0 else 0.0
        for col in range(grid.shape[1]):
            x0 = min(grid.xs[col], width)
            x1 = min(x0 + grid.patch_w, width)
            areas[row, col] = rows_total * max(x1 - x0, 0)
    return areas


async def classify_scene(
    *,
    project_id: int,
    settings: Settings,
    scene: Scene,
    run: TrainingRun,
    checkpoint: dict,
    method: str,
    accept_unverified_schema: bool = False,
    study_area_geometry: dict | None = None,
    study_area_crs: str | None = None,
) -> dict:
    """Classify one scene on its native grid and write its three products."""
    contract = require_compatible_model(
        run, checkpoint, scene, accept_unverified=accept_unverified_schema
    )

    def _compute():
        model = checkpoint["model"]
        resolution = checkpoint.get("resolution", "pixel")
        data, valid = _read_scene(scene, settings)
        if resolution == "pixel":
            grid = make_grid(scene.height, scene.width, 1, 1)
            X, pixel_valid = pixel_features(data)
            valid = valid & pixel_valid.reshape(scene.height, scene.width)
        else:
            grid = make_grid(
                scene.height, scene.width, checkpoint["patch_size"], checkpoint["stride"]
            )
            if grid.shape[0] * grid.shape[1] > _MAX_SCENE_CELLS:
                raise SceneClassificationError(
                    f"Scene grid would be {grid.shape[0]}x{grid.shape[1]} cells; "
                    "classify a smaller scene or train a pixel-resolution model"
                )
            X = patch_features(data, grid)
            # Cell validity: a cell is valid when it contains at least one valid
            # pixel of *this* scene (nodata collars must not become land cover).
            cell_valid = patch_validity(
                np.where(valid, 1.0, np.nan).astype(np.float32)[None, ...], grid
            ).reshape(grid.shape)
            valid = cell_valid
        raw = np.asarray(model.predict_proba(X))
        model_classes = [run.classes[int(index)] for index in model.classes_]
        probs = align_probabilities(raw, model_classes, run.classes)
        hard, prob, unc = maps_from_inference(probs, valid.reshape(-1), grid.shape, method)
        return resolution, grid, valid.reshape(grid.shape), hard, prob, unc

    try:
        resolution, grid, valid, hard, prob, unc = await anyio.to_thread.run_sync(_compute)
    except RasterError as exc:
        raise SceneClassificationError(str(exc)) from exc

    # Study area: the same pixel-centre test the dataset path uses, on the whole
    # scene. The rule is recorded because "inside the study area" is ambiguous.
    study = {"applied": False, "rule": "center-in-polygon", "note": "no study area configured"}
    if study_area_geometry:
        try:
            mask, note = await anyio.to_thread.run_sync(
                lambda: study_area_mask(
                    study_area_geometry,
                    study_area_crs,
                    scene.crs,
                    scene.transform,
                    region=(0, 0, scene.width, scene.height),
                    height=scene.height,
                    width=scene.width,
                    shape=grid.shape,
                )
            )
        except StudyAreaError as exc:
            raise SceneClassificationError(f"Study area cannot be applied: {exc}") from exc
        valid = valid & mask
        hard = np.where(valid, hard, 0)
        prob = prob * valid[None, :, :]
        unc = np.where(valid, unc, 0.0)
        study = {"applied": True, "rule": "center-in-polygon", "note": note}

    if not scene.crs or not scene.transform:
        raise SceneClassificationError(
            f"Scene {scene.id} has no CRS/affine; refusing to write an export that would "
            "claim a georeference it does not have"
        )

    # Areas, from this grid's own geometry.
    areas: dict
    try:
        row_areas, area_method = await anyio.to_thread.run_sync(
            lambda: pixel_areas(CRS.from_user_input(scene.crs), scene.transform, scene.height, scene.width)
        )
        if resolution == "pixel":
            areas = area_by_class(hard, valid, run.classes, row_areas)
        else:
            cell_areas = _cell_pixel_area(grid, row_areas, scene.height, scene.width)
            areas = area_by_class(hard, valid, run.classes, cell_areas)
        areas["method"] = area_method
        taxonomy = checkpoint.get("taxonomy") or {}
        interpretation = taxonomy.get("binary_interpretation")
        if interpretation in BINARY_MAPPINGS:
            areas["water"] = water_areas(areas, list(BINARY_MAPPINGS[interpretation]["water"]))
        areas["available"] = True
    except ValueError as exc:
        areas = {
            "available": False,
            "reason": str(exc),
            "per_class": [],
            "valid_pixels": int(np.asarray(valid).sum()),
        }

    transform = Affine(*[float(value) for value in scene.transform[:6]])
    meta = grid_metadata(
        grid, 0, 0, 1 if resolution == "pixel" else checkpoint["stride"],
        include_cells=resolution != "pixel",
    )
    meta.update(
        resolution="pixel" if resolution == "pixel" else "patch-cells",
        method=method,
        training_run_id=run.id,
        study_area_applied=study["applied"],
        study_area_note=study["note"],
        band_schema_verified=contract["verified"],
        band_schema_reason=contract["reason"],
        scene_id=scene.id,
    )

    export_dir = project_dir(settings, "exports", project_id)
    tag = f"scene{scene.id}_iter{run.iteration}_{uuid.uuid4().hex[:8]}"
    paths = {
        "hard": export_dir / f"scene_hard_{tag}.tif",
        "probability": export_dir / f"scene_probability_{tag}.tif",
        "uncertainty": export_dir / f"scene_uncertainty_{method}_{tag}.tif",
    }
    if resolution == "pixel":
        point_transform = pixel_transform(scene.transform, 0, 0)
        writers = {
            "hard": lambda: export_hard_geotiff(
                paths["hard"], hard, run.classes, scene.crs, point_transform, meta,
                resolution="pixel",
            ),
            "probability": lambda: export_probability_geotiff(
                paths["probability"], prob, run.classes, scene.crs, point_transform, meta,
                valid=valid, resolution="pixel",
            ),
            "uncertainty": lambda: export_uncertainty_geotiff(
                paths["uncertainty"], unc, run.classes, scene.crs, point_transform, method,
                meta, resolution="pixel",
            ),
        }
    else:
        writers = {
            "hard": lambda: export_hard_cells_geotiff(
                paths["hard"], hard, valid, grid, run.classes, scene.crs, transform,
                scene.height, scene.width, meta,
            ),
            "probability": lambda: export_probability_cells_geotiff(
                paths["probability"], prob, valid, grid, run.classes, scene.crs, transform,
                scene.height, scene.width, meta,
            ),
            "uncertainty": lambda: export_uncertainty_cells_geotiff(
                paths["uncertainty"], unc, valid, grid, run.classes, scene.crs, transform,
                method, scene.height, scene.width, meta,
            ),
        }

    artifacts: dict[str, dict] = {}
    for kind, write in writers.items():
        await anyio.to_thread.run_sync(write)
        identity = await anyio.to_thread.run_sync(lambda p=paths[kind]: file_identity(p))
        artifacts[kind] = {
            "path": str(paths[kind]),
            "name": paths[kind].name,
            "sha256": (identity or {}).get("sha256"),
            "size_bytes": (identity or {}).get("size_bytes"),
        }

    return {
        "grid": scene_grid(scene),
        "classes": list(run.classes),
        "contract": contract,
        "study_area": study,
        "areas": areas,
        "artifacts": artifacts,
        "resolution": resolution,
        "hard": hard,
        "probability": prob,
        "uncertainty": unc,
        "valid": valid,
        "transform": [float(value) for value in scene.transform[:6]],
        "method": method,
    }


def analysis_lineage(*, run: TrainingRun, scene: Scene, result: dict) -> dict:
    """The immutable provenance of one scene classification."""
    core = {
        "training_run_id": run.id,
        "checkpoint_sha256": run.checkpoint_sha256,
        "manifest_hash": (run.manifest or {}).get("hash"),
        "scene_content_sha256": scene.content_sha256,
        "scene_grid": result["grid"],
        "band_contract": result["contract"],
        "study_area": result["study_area"],
        "resolution": result["resolution"],
        "method": result["method"],
        "artifacts": {kind: entry.get("sha256") for kind, entry in result["artifacts"].items()},
    }
    return {**core, "analysis_digest": digest(core)}


def build_analysis(
    *, project_id: int, scene: Scene, run: TrainingRun, result: dict, method: str
) -> SceneAnalysis:
    lineage = analysis_lineage(run=run, scene=scene, result=result)
    return SceneAnalysis(
        project_id=project_id,
        scene_id=scene.id,
        training_run_id=run.id,
        resolution=result["resolution"],
        method=method,
        grid=result["grid"],
        classes=result["classes"],
        taxonomy=(run.manifest or {}).get("taxonomy"),
        contract=result["contract"],
        study_area=result["study_area"],
        artifacts=result["artifacts"],
        areas=result["areas"],
        lineage=lineage,
        created_at=utcnow(),
    )
