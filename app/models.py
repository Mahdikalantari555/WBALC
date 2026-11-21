"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    classes: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    study_area_geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    study_area_crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Versioned water-body taxonomy + label crosswalk. NULL = generic/legacy
    # project whose class list this application did not configure.
    taxonomy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    labels: Mapped[list["Label"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    training_runs: Mapped[list["TrainingRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    experiments: Mapped[list["Experiment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    exports: Mapped[list["Export"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    query_batches: Mapped[list["QueryBatch"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    # Phase 3-5 records have no `project` back-reference of their own; declaring the
    # cascade here keeps `DELETE /projects/{id}` from leaving orphans behind.
    scene_analyses: Mapped[list["SceneAnalysis"]] = relationship(cascade="all, delete-orphan")
    fusion_runs: Mapped[list["FusionRun"]] = relationship(cascade="all, delete-orphan")
    evaluation_protocols: Mapped[list["EvaluationProtocol"]] = relationship(
        cascade="all, delete-orphan"
    )
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(
        cascade="all, delete-orphan"
    )
    reference_areas: Mapped[list["ReferenceArea"]] = relationship(cascade="all, delete-orphan")
    research_plans: Mapped[list["ResearchPlan"]] = relationship(cascade="all, delete-orphan")
    research_reports: Mapped[list["ResearchReport"]] = relationship(cascade="all, delete-orphan")


class Scene(Base):
    """One independently georeferenced satellite acquisition under a project."""

    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    acquisition_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sensor: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    product_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transform: Mapped[list | None] = mapped_column(JSON, nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    pixel_size_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pixel_size_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_count: Mapped[int] = mapped_column(Integer, nullable=False)
    band_names: Mapped[list | None] = mapped_column(JSON, nullable=True)
    band_descriptions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    band_dtypes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    nodata_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mask_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    has_validity_mask: Mapped[bool] = mapped_column(default=False, nullable=False)
    bounds: Mapped[list | None] = mapped_column(JSON, nullable=True)
    polarization: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acquisition_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    orbit_direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    relative_orbit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_baseline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    native_band_resolutions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    acquisition_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    product_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The queryable Dataset row spawned with this scene (same immutable bytes).
    # Null for legacy scenes pending backfill or after the dataset was removed.
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="scenes")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(1024))
    crs: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transform: Mapped[list | None] = mapped_column(JSON, nullable=True)  # affine 6 coefficients
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bands: Mapped[int] = mapped_column(Integer)
    dtype: Mapped[str] = mapped_column(String(50))
    nodata: Mapped[float | None] = mapped_column(Float, nullable=True)
    bounds: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Ordered band identity (names/sensor/declared flag + digest). NULL means the
    # raster carries no declarable identity: never backfilled with guesses.
    band_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Content identity of the stored bytes, hashed while they were being written.
    # NULL = legacy upload: reported as unavailable, never recomputed as if it had
    # been recorded at registration time.
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Where this row came from: 'upload' (the operator's training raster) or
    # 'scene' (a queryable copy registered alongside a Scene). Client default
    # selection keys on this instead of guessing by name or recency.
    origin: Mapped[str] = mapped_column(String(10), default="upload", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="datasets")


class Label(Base):
    """One version of a label for a sample. Full history is retained."""

    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    sample_id: Mapped[str] = mapped_column(String(255), index=True)
    sample_type: Mapped[str] = mapped_column(String(20))  # point | polygon | patch
    geometry: Mapped[dict] = mapped_column(JSON)  # GeoJSON geometry
    coordinate_space: Mapped[str] = mapped_column(String(10), default="pixel")  # pixel | map
    class_name: Mapped[str] = mapped_column(String(255))
    # Text the annotator submitted when it differs from `class_name` (an alias).
    submitted_class_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Provenance: which durable query item (if any) this version answered.
    # NULL means the label was typed or imported directly — reported as manual,
    # never attributed to a query it did not come from.
    query_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="labels")


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    iteration: Mapped[int] = mapped_column(Integer)
    model_type: Mapped[str] = mapped_column(String(50))  # rf | lightgbm
    checkpoint_path: Mapped[str] = mapped_column(String(1024))
    classes: Mapped[list] = mapped_column(JSON)  # class order used by the model
    # The subset of `classes` this model actually learned (no labels for the rest).
    trained_classes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    n_samples: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # Immutable reproducibility manifest (inputs, label versions, config,
    # environment). NULL = run predates manifests: reported incomplete.
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checkpoint_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="training_runs")
    experiment: Mapped["Experiment | None"] = relationship(back_populates="runs")


class Experiment(Base):
    """A named group of runs kept for comparison.

    Membership is an association on the *run* (`experiments` never rewrites a run
    manifest or a score); adding a run to an experiment cannot change what the run
    recorded.
    """

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The question this comparison is meant to answer, plus the config the
    # experiment was declared with. Snapshotted, never recomputed from the runs.
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="experiments")
    runs: Mapped[list["TrainingRun"]] = relationship(back_populates="experiment")


class QueryBatch(Base):
    """One durable active-learning request: what was asked, of which pool, why.

    The batch is the scientific record of a selection. It is written in the same
    transaction as its items, so a failed query leaves nothing visible. Nothing
    here implies an authenticated operator: `note` is free text, and the app has
    no identity system.
    """

    __tablename__ = "query_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    strategy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # Seeded strategies record their seed; deterministic ones leave it NULL
    # rather than pretending a random draw happened.
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_size_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size_returned: Mapped[int] = mapped_column(Integer, nullable=False)
    # Candidate pool: grid geometry, eligibility rules, size and an ordered hash
    # of the eligible sample ids so two batches can be proved to share a pool.
    pool: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    model_iteration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    training_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="query_batches")
    items: Mapped[list["QueryItem"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="QueryItem.position"
    )


class QueryItem(Base):
    """One selected sample inside a batch, with its recorded decision."""

    __tablename__ = "query_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("query_batches.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)
    coords: Mapped[dict] = mapped_column(JSON, default=dict)
    geo_coords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # pending | labeled | rejected | deferred
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    decided_class: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The label version this decision produced, when one was submitted from here.
    label_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    batch: Mapped[QueryBatch] = relationship(back_populates="items")


class SceneAnalysis(Base):
    """One classification of one Scene on that Scene's native grid.

    Immutable record: it stores the grid it was computed on, the model and the
    schema contract that allowed the inference, the exports it wrote (with their
    checksums) and the area summary derived from them.
    """

    __tablename__ = "scene_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    training_run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(40), default="entropy", nullable=False)
    # The grid actually written: crs/transform/width/height, so a reader can prove
    # compatibility instead of assuming it.
    grid: Mapped[dict] = mapped_column(JSON, default=dict)
    classes: Mapped[list] = mapped_column(JSON, default=list)
    taxonomy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contract: Mapped[dict] = mapped_column(JSON, default=dict)
    study_area: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict)
    areas: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FusionRun(Base):
    """A declared late fusion of per-sensor derived products.

    Records the rule, the weights, the target grid and every source analysis, so
    the combined map can always be decomposed back into its per-sensor inputs.
    """

    __tablename__ = "fusion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    rule: Mapped[str] = mapped_column(String(40), nullable=False)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    target_grid: Mapped[dict] = mapped_column(JSON, default=dict)
    source_analysis_ids: Mapped[list] = mapped_column(JSON, default=list)
    missing_policy: Mapped[str] = mapped_column(String(40), default="require_all")
    alignment: Mapped[dict] = mapped_column(JSON, default=dict)
    classes: Mapped[list] = mapped_column(JSON, default=list)
    hard: Mapped[list | None] = mapped_column(JSON, nullable=True)
    areas: Mapped[dict] = mapped_column(JSON, default=dict)
    agreement: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationProtocol(Base):
    """A declared, persisted evaluation split.

    The split membership is stored (not re-derived), so a report generated later
    describes exactly the partition that produced the score.
    """

    __tablename__ = "evaluation_protocols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    split: Mapped[dict] = mapped_column(JSON, default=dict)
    split_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caveats: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationResult(Base):
    """Metrics produced by scoring a model on a protocol's held-out partition."""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_protocols.id", ondelete="CASCADE"), index=True
    )
    protocol_split_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_type: Mapped[str] = mapped_column(String(50))
    resolution: Mapped[str] = mapped_column(String(20), default="patch")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    calibration: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    caveats: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReferenceArea(Base):
    """An operator-supplied independent reference area for one scene.

    Area error is only computed against a record like this: the engine never uses
    its own mapped area as its own truth.
    """

    __tablename__ = "reference_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    water_area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(1024), nullable=False)
    uncertainty_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchPlan(Base):
    """A declared comparison: factors, levels, repetitions and limits, before runs."""

    __tablename__ = "research_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    protocol_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    comparison_metric: Mapped[str] = mapped_column(String(64), default="f1_macro")
    factors: Mapped[list] = mapped_column(JSON, default=list)
    repetitions: Mapped[int] = mapped_column(Integer, default=1)
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchReport(Base):
    """A generated report bundle: files, checksums and what it could not claim."""

    __tablename__ = "research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="complete")
    bundle: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict)
    caveats: Mapped[list] = mapped_column(JSON, default=list)
    digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer)
    training_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(20))  # hard | probability
    path: Mapped[str] = mapped_column(String(1024))
    region: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Checksum recorded right after the atomic write; downloads verify it.
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="exports")
