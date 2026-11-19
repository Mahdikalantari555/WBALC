"""Pydantic request / response schemas."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------- projects
WBALC_INTERNAL_CLASSES = ["open_water", "emergent_vegetation", "land"]
BinaryInterpretation = Literal["water_vs_non_water", "open_water_vs_other"]


def _validate_study_geometry(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if value.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("study-area geometry must be a GeoJSON Polygon or MultiPolygon")
    coordinates = value.get("coordinates")
    polygons = [coordinates] if value.get("type") == "Polygon" else coordinates
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("study-area geometry must contain polygon coordinates")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("study-area polygons must contain at least one ring")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("study-area rings must have at least four positions")
            positions = []
            for position in ring:
                if not isinstance(position, (list, tuple)) or len(position) < 2:
                    raise ValueError("study-area positions must be finite [x, y] coordinates")
                pair = position[:2]
                if not all(isinstance(item, (int, float)) and math.isfinite(item) for item in pair):
                    raise ValueError("study-area positions must be finite [x, y] coordinates")
                positions.append(list(pair))
            if positions[0] != positions[-1]:
                raise ValueError("study-area polygon rings must be closed")
    return value


class ClassificationConfig(BaseModel):
    internal_classes: list[str] = Field(default_factory=lambda: WBALC_INTERNAL_CLASSES.copy())
    binary_output_interpretation: BinaryInterpretation = "water_vs_non_water"
    # Explicit alias → canonical class mapping. `reed` is NOT a default: a project
    # has to say so, because emergent vegetation is not "reeds".
    label_aliases: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("internal_classes")
    @classmethod
    def validate_internal_classes(cls, value: list[str]) -> list[str]:
        if value != WBALC_INTERNAL_CLASSES:
            raise ValueError("WBALC internal classes must be open_water, emergent_vegetation, land")
        return value

    @field_validator("label_aliases")
    @classmethod
    def validate_aliases(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        from .services.taxonomy_service import TaxonomyError, normalise_aliases

        try:
            return normalise_aliases(value)
        except TaxonomyError as exc:  # surface as a 422, not a 500
            raise ValueError(str(exc)) from exc


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    classes: list[str] | None = Field(default=None, min_length=2)
    description: str = ""
    status: str = "active"
    study_area_geometry: dict[str, Any] | None = None
    study_area_crs: str | None = Field(default=None, max_length=255)
    classification_config: ClassificationConfig = Field(default_factory=ClassificationConfig)
    # Opt out of the WBALC water taxonomy on purpose. Without this flag a project
    # whose classes are not the water topology is refused, rather than silently
    # given water semantics it does not have.
    generic_classes: bool = False

    @field_validator("study_area_geometry")
    @classmethod
    def study_area_valid(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_study_geometry(value)

    @model_validator(mode="after")
    def geometry_requires_crs(self):
        if self.study_area_geometry is not None and not self.study_area_crs:
            raise ValueError("study_area_crs is required when study_area_geometry is provided")
        return self

    @model_validator(mode="after")
    def classes_match_taxonomy(self):
        """`classes` and the taxonomy must not contradict each other."""
        if self.classes is None:
            return self
        if self.generic_classes:
            return self
        if self.classes != WBALC_INTERNAL_CLASSES:
            raise ValueError(
                "classes must be the WBALC water taxonomy "
                f"({', '.join(WBALC_INTERNAL_CLASSES)}) in that order; "
                "pass generic_classes=true to create a project with its own class list "
                "and no water crosswalk"
            )
        return self

    @field_validator("classes")
    @classmethod
    def classes_unique_nonempty(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [c.strip() for c in v]
        if any(not c for c in cleaned):
            raise ValueError("class names must be non-empty")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("class names must be unique")
        return cleaned


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    classes: list[str] | None = None
    description: str | None = None
    status: str | None = None
    study_area_geometry: dict[str, Any] | None = None
    study_area_crs: str | None = Field(default=None, max_length=255)
    classification_config: ClassificationConfig | None = None
    # Switching an existing project into (or out of) the water taxonomy is an
    # explicit migration decision, never implicit.
    generic_classes: bool | None = None

    @field_validator("study_area_geometry")
    @classmethod
    def study_area_valid(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_study_geometry(value)

    @model_validator(mode="after")
    def geometry_requires_crs(self):
        if self.study_area_geometry is not None and not self.study_area_crs:
            raise ValueError("study_area_crs is required when study_area_geometry is provided")
        return self

    @field_validator("classes")
    @classmethod
    def classes_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return ProjectCreate.classes_unique_nonempty(v)


class TaxonomyOut(BaseModel):
    """Read-only description of a project's class semantics."""

    taxonomy_version: str | None = None
    source: str  # "default" | "project" | "legacy"
    classes: list[str]
    display_names: dict[str, str]
    aliases: dict[str, list[str]]
    binary: dict[str, Any]


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    classes: list[str]
    status: str
    study_area_geometry: dict[str, Any] | None = None
    study_area_crs: str | None = None
    classification_config: ClassificationConfig
    # Stored taxonomy snapshot (version, class order, crosswalk, interpretation).
    # Null for a generic/legacy project that never opted into the water taxonomy.
    # `GET /projects/{id}/taxonomy` derives the richer, computed description.
    taxonomy: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- datasets
class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    crs: str | None
    transform: list[float] | None
    width: int
    height: int
    bands: int
    dtype: str
    nodata: float | None
    bounds: list[float] | None
    # Ordered band identity as recorded at upload; `declared` is False when the
    # file carried no usable names, so callers must not read it as compatibility.
    band_schema: dict | None = None
    created_at: datetime
    # Computed metadata for clients (frontend rendering / progress display).
    size_bytes: int | None = 0
    patch_grid: dict | None = None
    # Content identity recorded while the bytes were written. None = legacy
    # upload whose bytes were never hashed at registration time.
    content_sha256: str | None = None


class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    acquisition_datetime: datetime | None
    platform: str | None
    sensor: Literal["Sentinel-1", "Sentinel-2"]
    product_type: str | None
    product_level: str | None
    source_filename: str
    storage_reference: str
    crs: str | None
    transform: list[float] | None
    width: int
    height: int
    pixel_size_x: float | None
    pixel_size_y: float | None
    resolution_x: float | None
    resolution_y: float | None
    band_count: int
    band_names: list[str | None] | None
    band_descriptions: list[str | None] | None
    band_dtypes: list[str] | None
    nodata_values: list[float | None] | None
    mask_flags: list[list[str]] | None
    has_validity_mask: bool
    bounds: list[float] | None
    polarization: list[str] | None
    acquisition_mode: str | None
    orbit_direction: str | None
    relative_orbit: int | None
    processing_baseline: str | None
    native_band_resolutions: dict[str, float] | None
    acquisition_metadata: dict[str, Any] | None
    product_metadata: dict[str, Any] | None
    uploaded_at: datetime
    registered_at: datetime
    size_bytes: int = 0


class SceneSpatialOut(BaseModel):
    scene_id: int
    crs: str | None
    transform: list[float] | None
    bounds: list[float] | None
    width: int
    height: int
    pixel_size_x: float | None
    pixel_size_y: float | None
    resolution_x: float | None
    resolution_y: float | None
    has_validity_mask: bool
    nodata_values: list[float | None] | None
    grid: dict[str, Any]


# ---------------------------------------------------------------- labels
class Geometry(BaseModel):
    type: Literal["Point", "Polygon"]
    coordinates: list[Any]

    @field_validator("coordinates")
    @classmethod
    def coordinates_match_type(cls, v: list[Any], info) -> list[Any]:
        gtype = info.data.get("type")
        if gtype == "Point":
            if len(v) < 2 or not all(isinstance(c, (int, float)) and math.isfinite(c) for c in v[:2]):
                raise ValueError("Point coordinates must be finite [x, y]")
        elif gtype == "Polygon":
            if not v or not isinstance(v[0], list) or len(v[0]) < 1:
                raise ValueError("Polygon coordinates must contain rings")
            for ring in v:
                if not isinstance(ring, list) or len(ring) < 4:
                    raise ValueError("Polygon rings must have at least four positions")
                for position in ring:
                    if not isinstance(position, (list, tuple)) or len(position) < 2 or not all(isinstance(c, (int, float)) and math.isfinite(c) for c in position[:2]):
                        raise ValueError("Polygon positions must contain finite [x, y] coordinates")
                if list(ring[0][:2]) != list(ring[-1][:2]):
                    raise ValueError("Polygon rings must be closed")
                area = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))
                if abs(area) < 1e-15:
                    raise ValueError("Polygon rings must have non-zero area")
                segments = list(zip(ring[:-1], ring[1:]))
                def orientation(a, b, c):
                    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                for i, (a, b) in enumerate(segments):
                    for j in range(i + 1, len(segments)):
                        if j == i + 1 or (i == 0 and j == len(segments) - 1):
                            continue
                        c, d = segments[j]
                        if orientation(a, b, c) * orientation(a, b, d) < 0 and orientation(c, d, a) * orientation(c, d, b) < 0:
                            raise ValueError("Polygon rings must not self-intersect")
        return v


class LabelCreate(BaseModel):
    sample_id: str | None = None
    geometry: Geometry
    class_name: str = Field(min_length=1)
    # Original text as the annotator submitted it. When it is an alias it is
    # recorded here and kept next to the resolved canonical class, so the
    # mapping stays auditable instead of being rewritten away.
    submitted_class_name: str | None = None
    iteration: int = Field(default=0, ge=0)
    dataset_id: int | None = None
    coordinate_space: Literal["pixel", "map"] = "pixel"
    sample_resolution: Literal["patch", "pixel"] = "patch"
    coordinate_crs: str | None = None
    # Where the annotator saw this sample. Supplying it links the label version
    # to that durable query item; omitting it keeps manual/legacy provenance.
    query_batch_id: int | None = None
    query_item_id: int | None = None


class LabelBatchCreate(BaseModel):
    labels: list[LabelCreate] = Field(min_length=1)
    auto_train: bool = False
    model_type: Literal["rf", "lightgbm"] = "rf"


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    dataset_id: int | None
    sample_id: str
    sample_type: str
    submitted_class_name: str | None = None
    geometry: dict
    coordinate_space: str
    class_name: str
    iteration: int
    version: int
    query_batch_id: int | None = None
    query_item_id: int | None = None
    # manual | query — reported, never inferred from anything but the stored link.
    provenance: str = "manual"
    created_at: datetime


# ---------------------------------------------------------------- query
class QueryRequest(BaseModel):
    strategy: Literal["uncertainty", "diversity", "hybrid", "som", "random"] = "uncertainty"
    batch_size: int = Field(default=10, ge=1, le=10000)
    method: Literal["least_confidence", "margin", "entropy"] = "least_confidence"
    dataset_id: int | None = None
    include_embedding: bool = False
    exclude_labeled: bool = True
    hybrid_pool_multiplier: int = Field(default=5, ge=1, le=100)
    patch_size: int | None = Field(default=None, ge=2, le=512)
    stride: int | None = Field(default=None, ge=1, le=512)
    som_rows: int | None = Field(default=None, ge=2, le=32)
    som_cols: int | None = Field(default=None, ge=2, le=32)
    som_epochs: int = Field(default=50, ge=5, le=500)
    som_cell: tuple[int, int] | None = None
    # Seeded baseline. Only used by strategy='random'; the seed is always
    # recorded, and the default is the engine's configured random_state.
    seed: int | None = Field(default=None, ge=0)
    # Free-text operator note. It is not an identity claim: the app has no
    # authentication, so this is never presented as an author.
    note: str | None = Field(default=None, max_length=2000)


class QuerySample(BaseModel):
    sample_id: str
    dataset_id: int
    coords: dict  # patch bbox: row, col, x0, y0, x1, y1 (pixels) + center
    geo_coords: dict | None = None  # bbox/center in dataset CRS when available
    prediction: str | None = None
    confidence: float | None = None
    uncertainty: float | None = None
    embedding: list[float] | None = None


class QueryPoolOut(BaseModel):
    """The eligible candidate pool a batch sampled from."""

    size: int
    hash: str
    patch_size: int
    stride: int
    grid: dict
    grid_cells: int
    n_labeled_patches: int
    exclude_labeled: bool
    eligibility: str


class QueryResponse(BaseModel):
    # Durable identity of this selection. Present on every successful query, so
    # the browser queue can always be reloaded from the server.
    batch_id: int
    strategy: str
    method: str | None
    strategy_version: str = "query-v1"
    seed: int | None = None
    batch_size: int
    requested_size: int | None = None
    model_iteration: int | None
    training_run_id: int | None = None
    dataset_id: int | None = None
    created_at: datetime | None = None
    pool: QueryPoolOut | None = None
    # Human-readable explanations of deliberate degradations (e.g. a pixel
    # checkpoint that cannot score patch embeddings). Empty when none apply.
    notes: list[str] = Field(default_factory=list)
    samples: list[QuerySample]


# ------------------------------------------------- query batch history (Phase 2)
class QueryDecisionRequest(BaseModel):
    status: Literal["labeled", "rejected", "deferred", "pending"]
    class_name: str | None = None
    label_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


class QueryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    sample_id: str
    dataset_id: int
    row: int
    col: int
    coords: dict
    geo_coords: dict | None = None
    score: float | None = None
    uncertainty: float | None = None
    prediction: str | None = None
    confidence: float | None = None
    status: str
    decided_class: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    label_id: int | None = None


class QueryBatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    dataset_id: int | None = None
    strategy: str
    method: str | None
    strategy_version: str
    seed: int | None = None
    batch_size_requested: int
    batch_size_returned: int
    pool: dict | None = None
    parameters: dict = Field(default_factory=dict)
    model_iteration: int | None = None
    training_run_id: int | None = None
    notes: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: datetime
    # Decision counts per state, so a list view needs no per-item fetch.
    decisions: dict[str, int] = Field(default_factory=dict)


class QueryBatchOut(QueryBatchSummary):
    items: list[QueryItemOut] = Field(default_factory=list)


# ------------------------------------------------- lineage / experiments (Phase 3)
class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    hypothesis: str | None = None
    config: dict[str, Any] | None = None


class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    hypothesis: str | None = None
    config: dict[str, Any] | None = None


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str
    hypothesis: str | None = None
    config: dict | None = None
    created_at: datetime
    updated_at: datetime
    run_ids: list[int] = Field(default_factory=list)


class ExperimentMembership(BaseModel):
    training_run_ids: list[int] = Field(min_length=1)


class RunLineageOut(BaseModel):
    """What a run was actually made of, and what is missing from its record."""

    run_id: int
    iteration: int
    experiment_id: int | None = None
    # legacy | complete | incomplete
    lineage_status: str
    manifest: dict | None = None
    manifest_hash: str | None = None
    missing: list[str] = Field(default_factory=list)
    artifact: dict | None = None
    notes: list[str] = Field(default_factory=list)


class RunComparisonRow(BaseModel):
    run_id: int
    iteration: int
    model_type: str
    accuracy: float | None = None
    f1_macro: float | None = None
    n_samples: int
    evaluation: str | None = None
    lineage_status: str
    manifest_hash: str | None = None
    label_snapshot_hash: str | None = None
    input_hashes: dict[str, str | None] = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    environment_revision: str | None = None


class RunComparisonOut(BaseModel):
    experiment_id: int | None = None
    project_id: int
    runs: list[RunComparisonRow]
    # Fields on which the compared runs genuinely differ. Scores are only
    # presented as comparable when `comparable` is true.
    differences: dict[str, list] = Field(default_factory=dict)
    comparable: bool = False
    caveats: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- training
class TrainRequest(BaseModel):
    model_type: Literal["rf", "lightgbm"] = "rf"
    resolution: Literal["patch", "pixel"] = "patch"
    evaluation_strategy: Literal["random", "spatial"] = "random"
    iteration: int | None = Field(default=None, ge=0)
    test_size: float | None = Field(default=None, gt=0.0, lt=1.0)
    params: dict[str, Any] = Field(default_factory=dict)
    # Combining datasets whose band identity cannot be proven equivalent is
    # refused unless the caller explicitly accepts an unverified schema.
    accept_unverified_schema: bool = False


class MetricsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    iteration: int
    model_type: str
    n_samples: int
    accuracy: float
    f1_macro: float
    f1_weighted: float
    confusion_matrix: list[list[int]]
    per_class: dict[str, dict[str, float]]
    classes: list[str]
    evaluation: str
    evaluation_details: str | None = None
    # Configuration behind the metrics, so a score is never context-free:
    # `resolution` says which feature family produced it, `evaluation_strategy`
    # whether a spatial or random holdout was requested, and the counts say how
    # much data the score actually saw.
    resolution: str = "patch"
    evaluation_strategy: str | None = None
    n_train: int | None = None
    n_test: int | None = None
    held_out_groups: int | None = None
    per_class_iou: dict[str, float] = Field(default_factory=dict)
    created_at: datetime


class RunSummaryOut(MetricsOut):
    """A run plus its lineage pointer, so a list view can show completeness."""

    manifest_hash: str | None = None
    lineage_status: str = "legacy"
    experiment_id: int | None = None
    checkpoint_sha256: str | None = None


class TrainResponse(BaseModel):
    id: int
    project_id: int
    iteration: int
    model_type: str
    resolution: str = "patch"
    checkpoint: str
    n_samples: int
    metrics: MetricsOut


# ---------------------------------------------------------------- inference
class Region(BaseModel):
    """Pixel-space window: x = column, y = row."""

    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(gt=0)
    y1: int = Field(gt=0)


class PredictRequest(BaseModel):
    # Required: pixel inference must never fall back to "the newest upload".
    dataset_id: int = Field(ge=1)
    region: Region | None = None
    iteration: int | None = Field(default=None, ge=0)
    include_maps: bool = True
    # Deliberate, recorded acknowledgement that the raster's band identity could
    # not be proven to match the model's. Required when verification fails.
    accept_unverified_schema: bool = False


class PredictResponse(BaseModel):
    project_id: int
    dataset_id: int
    model_iteration: int
    classes: list[str]
    # "pixel" = one independent prediction per source pixel; "patch" = one
    # prediction per patch cell (see grid/patch_size/stride).
    resolution: str = "patch"
    region: Region
    grid_shape: list[int]  # [rows, cols] of the patch grid
    patch_size: int
    stride: int
    hard_map: list[list[int]] | None = None
    # [class][row][col]; None where the cell has no valid source pixels.
    probability_map: list[list[list[float | None]]] | None = None
    uncertainty_map: list[list[float | None]] | None = None  # per-patch, 0..1
    uncertainty_method: str | None = None
    valid_map: list[list[bool]] | None = None  # False = patch has no valid pixels
    # Provenance: what produced these numbers, and which masks were applied.
    training_run_id: int | None = None
    band_schema_verified: bool = False
    band_schema_reason: str | None = None
    schema_override: bool = False
    study_area_applied: bool = False
    study_area_note: str | None = None
    # What a derived binary product would (or did) mean, and whether it is
    # available at all. The three-class maps above remain the source product.
    binary: BinarySummary | None = None
    exports: dict[str, str]  # type -> download URL


class MapGridOut(BaseModel):
    """Where the patch cells live in the source raster."""

    rows: int
    cols: int
    patch_size: int
    stride: int
    region: Region


class BinarySummary(BaseModel):
    """Derived binary water interpretation available from a three-class product."""

    interpretation: str
    version: str
    available: bool
    # class id -> "water" | "non_water", for the classes the model actually has
    mapping: dict[str, str] = Field(default_factory=dict)
    source_classes: list[str] = Field(default_factory=list)
    missing_classes: list[str] = Field(default_factory=list)
    reason: str | None = None
    taxonomy_version: str | None = None
    exports: dict[str, str] = Field(default_factory=dict)


class MapFieldOut(BaseModel):
    """One grid-aligned scalar field for the map layers (classification/uncertainty)."""

    layer: str  # hard | uncertainty
    method: str | None = None
    project_id: int
    dataset_id: int
    model_iteration: int
    training_run_id: int
    classes: list[str]
    resolution: str = "patch"
    grid: MapGridOut
    # rows x cols; class indices for `hard`, 0..1 floats (None where invalid)
    # for `uncertainty`.
    values: list[list[int | float | None]]
    valid: list[list[bool]]
    min: float | None = None
    max: float | None = None
    stale: bool = False
    band_schema_verified: bool = False
    band_schema_reason: str | None = None
    study_area_applied: bool = False
    study_area_note: str | None = None
    # Derived product plan; None when the project has no water taxonomy.
    binary: BinarySummary | None = None
    exports: dict[str, str]


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    dataset_id: int
    training_run_id: int | None
    type: str
    region: dict | None
    path: str
    created_at: datetime
    # Derived for the UI: which iteration produced it, whether a newer training
    # run exists, and the dataset filename so a list entry is self-describing.
    iteration: int | None = None
    method: str | None = None
    stale: bool = False
    dataset_name: str | None = None
    # Integrity, as recorded at write time and observed now.
    sha256: str | None = None
    size_bytes: int | None = None
    integrity: str | None = None


# ---------------------------------------------------------------- self-organizing map
class SomRequest(BaseModel):
    dataset_id: int | None = None
    rows: int | None = Field(default=None, ge=2, le=32)
    cols: int | None = Field(default=None, ge=2, le=32)
    epochs: int = Field(default=50, ge=5, le=500)
    sigma: float | None = Field(default=None, gt=0.0, le=32.0)
    learning_rate: float = Field(default=0.7, gt=0.0, le=1.0)
    patch_size: int | None = Field(default=None, ge=2, le=512)
    stride: int | None = Field(default=None, ge=1, le=512)


class SomCell(BaseModel):
    row: int
    col: int
    hit_count: int
    labeled_count: int
    unlabeled_count: int
    u_value: float
    quantization_error: float
    dominant_label: str | None = None
    label_counts: dict[str, int] = Field(default_factory=dict)
    predicted_class: str | None = None
    prediction_counts: dict[str, int] = Field(default_factory=dict)
    mean_confidence: float | None = None
    mean_uncertainty: float | None = None
    band_means: list[float]
    band_profile: list[float]
    representative_sample_id: str | None = None
    sample_ids: list[str] = Field(default_factory=list)


class SomResponse(BaseModel):
    project_id: int
    dataset_id: int
    rows: int
    cols: int
    epochs: int
    total_patches: int
    # Patches with at least one valid source pixel; the rest are nodata and are
    # excluded from the fit, the hit grid and every cell's sample list.
    valid_patches: int = 0
    nodata_patches: int = 0
    labeled_patches: int
    active_neurons: int
    quantization_error: float
    topographic_error: float
    model_iteration: int | None = None
    # Why supervised annotations are absent, when a checkpoint exists but cannot
    # annotate patch cells (band-count or resolution mismatch).
    model_note: str | None = None
    bands: int
    classes: list[str]
    u_matrix: list[list[float]]
    hit_grid: list[list[int]]
    cells: list[SomCell]


class SomClassifyRequest(BaseModel):
    dataset_id: int | None = None
    rows: int = Field(default=4, ge=2, le=32)
    cols: int = Field(default=4, ge=2, le=32)
    n_clusters: int | None = Field(default=None, ge=2, le=256)
    epochs: int = Field(default=50, ge=5, le=500)
    sigma: float | None = Field(default=None, gt=0.0, le=32.0)
    learning_rate: float = Field(default=0.7, gt=0.0, le=1.0)
    resolution: Literal["pixel", "patch"] = "pixel"
    region: Region | None = None
    patch_size: int | None = Field(default=None, ge=2, le=512)
    stride: int | None = Field(default=None, ge=1, le=512)
    max_train_samples: int = Field(default=25000, ge=64, le=250000)
    include_map: bool = True


class SomClusterSummary(BaseModel):
    cluster_id: int
    label: str
    color: list[int]
    pixel_count: int
    fraction: float
    band_means: list[float]
    band_profile: list[float]
    neurons: list[list[int]]


class SomClassifyResponse(BaseModel):
    project_id: int
    dataset_id: int
    export_id: int
    rows: int
    cols: int
    epochs: int
    n_clusters: int
    resolution: str
    region: Region
    shape: list[int]
    total_valid: int
    nodata_count: int
    quantization_error: float
    topographic_error: float
    u_matrix: list[list[float]]
    neuron_clusters: list[list[int]]
    neuron_hits: list[list[int]]
    clusters: list[SomClusterSummary]
    cluster_map: list[list[int]] | None = None
    exports: dict[str, str]


# ---------------------------------------- scene classification / temporal (Phase 4)
class PixelAreaMethod(BaseModel):
    kind: Literal["projected", "geographic", "unknown", "other"]
    supported: bool = True
    unit: str | None = None
    metres_per_unit: float | None = None
    ellipsoid: str | None = None
    pixel_area_m2: float | None = None
    varies_by_row: bool | None = None
    row_area_min_m2: float | None = None
    row_area_max_m2: float | None = None
    reason: str | None = None
    note: str | None = None


class ClassAreaOut(BaseModel):
    class_index: int
    class_name: str
    valid_pixels: int
    area_m2: float
    area_ha: float
    share_of_valid: float


class WaterAreaOut(BaseModel):
    water_classes: list[str]
    area_m2: float
    area_ha: float
    valid_area_m2: float
    share_of_valid: float


class AreaSummaryOut(BaseModel):
    available: bool = True
    reason: str | None = None
    per_class: list[ClassAreaOut] = []
    valid_pixels: int = 0
    invalid_pixels: int = 0
    total_pixels: int = 0
    coverage: float = 0.0
    valid_area_m2: float = 0.0
    valid_area_ha: float = 0.0
    pixel_area_m2_mean: float = 0.0
    method: PixelAreaMethod | None = None
    water: WaterAreaOut | None = None


class SceneClassificationRequest(BaseModel):
    iteration: int | None = None
    method: str = "entropy"
    accept_unverified_schema: bool = False


class SceneAnalysisSummary(BaseModel):
    id: int
    project_id: int
    scene_id: int
    training_run_id: int
    resolution: str
    method: str
    classes: list[str]
    grid: dict
    contract: dict
    study_area: dict
    artifacts: dict
    areas: AreaSummaryOut
    lineage: dict
    created_at: datetime


class SceneClassificationResponse(BaseModel):
    analysis: SceneAnalysisSummary
    scene_id: int
    acquisition_datetime: datetime | None = None
    sensor: str | None = None


class TransitionOut(BaseModel):
    from_: str = Field(alias="from")
    to: str
    pixels: int
    area_m2: float
    area_ha: float

    model_config = {"populate_by_name": True}


class TransitionMatrixOut(BaseModel):
    classes: list[str]
    matrix: list[list[int]]
    matrix_area_m2: list[list[float]]
    joint_valid_pixels: int
    joint_valid_area_m2: float
    joint_valid_area_ha: float
    changed_pixels: int
    changed_area_m2: float
    changed_area_ha: float
    unchanged_pixels: int
    changes: list[dict]
    denominator: str


class DateAreaPoint(BaseModel):
    scene_id: int
    analysis_id: int
    acquisition_datetime: datetime | None = None
    sensor: str | None = None
    valid_area_m2: float
    coverage: float
    per_class: list[ClassAreaOut]
    water: WaterAreaOut | None = None


class TemporalSeriesOut(BaseModel):
    project_id: int
    dates: list[DateAreaPoint]
    classes: list[str]
    alignment: dict
    caveats: list[str] = []


class AlignmentRequest(BaseModel):
    reference_scene_id: int
    resampling: Literal["nearest"] = "nearest"


class TemporalCompareRequest(BaseModel):
    before_scene_id: int
    after_scene_id: int
    reference_scene_id: int | None = None
    resampling: Literal["nearest"] = "nearest"


class GridMismatchOut(BaseModel):
    error: str
    differences: list[dict]
    reference_scene_id: int | None = None
    candidate_scene_id: int | None = None
    resampling_options: list[str] = []
    hint: str


class TemporalCompareResponse(BaseModel):
    before_scene_id: int
    after_scene_id: int
    classes: list[str]
    alignment: dict
    transitions: TransitionMatrixOut
    before: DateAreaPoint
    after: DateAreaPoint
    lineage: dict
    caveats: list[str] = []


class FusionRequest(BaseModel):
    name: str = ""
    rule: Literal[
        "weighted_probability",
        "weighted_vote",
        "priority",
        "early_fusion",
        "raw_band_fusion",
    ]
    target_scene_id: int
    analysis_ids: list[int]
    weights: dict[str, float] = {}
    priority: list[int] = []
    missing_policy: Literal["require_all", "renormalise"] = "require_all"


class FusionSourceOut(BaseModel):
    analysis_id: int
    scene_id: int
    sensor: str
    weight: float
    grid_aligned: bool
    analysis_digest: str | None = None


class FusionResponse(BaseModel):
    id: int
    project_id: int
    name: str
    rule: str
    weights: dict
    target_grid: dict
    alignment: dict
    missing_policy: str
    sources: list[FusionSourceOut]
    classes: list[str]
    areas: AreaSummaryOut | None = None
    agreement: dict
    artifacts: dict
    lineage: dict
    created_at: datetime


class EarlyFusionRejected(BaseModel):
    error: str
    detail: str
    supported_rules: list[str]
