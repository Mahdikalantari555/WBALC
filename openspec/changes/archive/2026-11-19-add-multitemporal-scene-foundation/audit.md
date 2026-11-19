# Repository and RSAL audit

## WBALC repository before this change

The WBALC working tree contained only `README.md` (`# WBALC`). There was no application code, OpenSpec configuration, backend, frontend, schema, migration, raster service, or tests to audit or preserve. The working tree was clean on the assigned branch.

## RSAL source inspected

The linked repository was cloned for inspection at upstream `main` commit `01353aab1822df802d8193a02ab91915f4947ee7`. Inspected the repository tree and its FastAPI app configuration, async SQLAlchemy database/models/schemas, project and dataset API conventions, storage helpers, rasterio service, API dependencies, frontend package/types/hooks/dataset workspace components, test fixtures/API tests, requirements, and prior OpenSpec change format.

## Findings

- Reusable architecture: FastAPI router/dependency patterns; async SQLAlchemy models and request schemas; local storage path helpers; rasterio-based GeoTIFF validation and metadata; synthetic GeoTIFF pytest fixtures; Next.js/React Query workspace and UI components.
- Adaptation required: RSAL `Dataset` has raster-level metadata but no acquisition/sensor identity or temporal metadata; project classes are free-form and require at least two values; there is no explicit schema migration runner (`init_db` relies on `metadata.create_all`, which does not evolve existing tables); frontend imagery is exposed as one dataset library and upload is not accompanied by sensor/acquisition fields.
- Important incompatibility: existing processing and UI code selects one dataset and assumes its band count/grid for a given operation. It must not imply that independent scenes are pixel-aligned or share a band schema. The new scene APIs therefore describe and preserve independent sources without changing legacy pixel-processing semantics.
- OpenSpec: upstream has historical change folders with proposal/design/tasks and capability delta specs, but no root config/current spec catalog. WBALC will establish an explicit `spec-driven` config and a focused change with proposal, design, complete task plan, and capability requirements.

## Proposed WBALC change

Add an explicit project classification configuration (`open_water`, `emergent_vegetation`, `land`, plus binary export interpretation), optional study geometry/CRS, and a new `Scene` entity with common raster grid metadata plus sensor-specific metadata fields and a flexible JSON metadata payload. Preserve legacy `Dataset` records and existing processing routes. Add versioned idempotent additive migrations, a dedicated scene upload/list/detail/spatial/delete API, raster grid comparison utilities, and a lightweight project/scene frontend flow using the existing design system.

## Risks and constraints

- Do not silently migrate old datasets into scenes without reliable acquisition/sensor data; keep legacy rows intact.
- Do not reproject, resample, mutate, or replace uploads during ingestion.
- Rasterio's reported bounds are axis-aligned envelopes; the affine transform remains authoritative for rotated grids.
- Acquisition time can be absent; null dates must sort deterministically without pretending to be observations at a particular time.
- Scene deletion must remove only that scene's stored source and row, not its project or other scenes.
- Keep existing one-dataset classifier/AL operations isolated; multi-scene computation is deferred.
