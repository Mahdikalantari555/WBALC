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
    exports: Mapped[list["Export"]] = relationship(back_populates="project", cascade="all, delete-orphan")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="training_runs")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer)
    training_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(20))  # hard | probability | som
    path: Mapped[str] = mapped_column(String(1024))
    region: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="exports")
