## Why

RSAL's inherited `Dataset` represents raster properties for a single uploaded scene but has no first-class acquisition identity, sensor distinction, or project-level scene collection. WBALC must retain independent Sentinel-1 and Sentinel-2 acquisitions, including missing or irregular dates and native grids that may differ. Treating every upload as a dataset with assumed band/grid compatibility makes multi-temporal research ambiguous and risks false pixel alignment.

## What Changes

- Add project study-area metadata and a validated WBALC classification configuration, preserving the distinction between three internal classes and optional binary output interpretation.
- Add independently persisted project scenes with acquisition/platform/sensor metadata, sensor-specific fields, complete band/raster metadata, native CRS/affine grid/dimensions/resolution/bounds, mask/NoData indicators, and upload/registration timestamps.
- Establish a GeoTIFF-only ingestion contract that validates and inspects a source, retains its original bytes, records metadata, and never reprojects, resamples, interpolates, or overwrites it.
- Add explicit grid-comparison utilities and separate future categorical/continuous resampling policy concepts; no target analysis resolution is selected.
- Add explicit, idempotent additive database migrations and scene project API routes for creation/list/detail/spatial metadata/deletion.
- Add the minimum project and scene frontend flow for creating/selecting a project, supplying sensor/acquisition metadata, upload, and temporally ordered scene inspection.

## Capabilities

### New Capabilities
- `study-projects`: project study-area and classification configuration.
- `scene-ingestion`: project-scoped multi-sensor scene registration and metadata APIs.
- `raster-grid-integrity`: explicit native-grid metadata and compatibility classification.
- `scene-library`: minimum frontend study project and scene upload/list/inspection workflow.

### Modified Capabilities
- `dataset-ingestion`: existing single-scene processing routes remain compatible; the new scene contract is additive and does not infer cross-scene alignment.

## Impact

- Backend: existing FastAPI/SQLAlchemy/rasterio patterns, new `Scene` model/schemas/service/router, explicit migration runner, and raster metadata extraction.
- Persistence: additive Project columns and a new scenes table; existing Dataset/Label/TrainingRun/Export data remains untouched.
- API: project schema additions and new `/projects/{project_id}/scenes` endpoints.
- Frontend: extend existing workspace with study project metadata and a focused scene collection/upload/inspection view.
- Tests: synthetic GeoTIFF fixtures for sensor, metadata, masks, grid and lifecycle scenarios.

## Explicit Non-goals

No automatic Sentinel download or catalog integration; no SAR/atmospheric preprocessing; no sensor fusion or temporal compositing; no water indices; no classifier, training, inference, or Active Learning changes; no water-area analytics/charts; no Zarr, cloud jobs, or distributed processing. The legacy classifier remains scoped to its existing single selected dataset.
