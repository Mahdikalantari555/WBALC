## Context

The WBALC repository was an empty shell. The linked RSAL baseline supplies FastAPI, async SQLAlchemy, rasterio, local file storage, a Next.js frontend, and synthetic raster tests. Its `Dataset` model and processing routes are intentionally single-dataset oriented. The implementation will add a separate `Scene` domain and preserve those legacy paths rather than forcing a risky wholesale conversion.

## Goals / Non-Goals

**Goals:** First-class project configuration and independent scene registration; complete native raster metadata; immutable GeoTIFF ingestion; explicit grid comparison; isolated scene deletion; additive migrations; a small frontend scene library.

**Non-goals:** Any multi-scene pixel processing or automatic harmonization, classifier changes, downloads, catalogs, or Active Learning.

## Decisions

- **Scene is distinct from Dataset.** Existing Dataset remains the compatibility unit used by the inherited processing pipeline. A Scene records a source acquisition and owns its file. No implicit Dataset-to-Scene migration is performed because legacy uploads may lack sensor/acquisition facts.
- **Project defaults are WBALC semantics.** New projects default to the ordered internal classes `open_water`, `emergent_vegetation`, `land`. A binary export setting selects `water_vs_non_water` (open water + emergent vegetation are water) or `open_water_vs_other`; internal classes are never collapsed.
- **Metadata is hybrid.** Searchable common fields and the explicitly important Sentinel-1/2 fields are typed columns. Band names/descriptions/dtypes and extensible source/product metadata are JSON so sensors with distinct band vocabularies are not forced into a shared schema.
- **Acquisition time is nullable.** Accept ISO-8601 time with offset and normalize to UTC. Scene lists sort known acquisition times newest-first, then unknown dates last; ties are stable by registration time and ID. Duplicate acquisition times are allowed.
- **Source immutability.** Stream uploads into a unique project-scoped file; inspect via rasterio; commit the scene only after validation; on failure remove only the new temporary source. No write mode, warp, or resampling is used. Store mask flags and per-band mask/NoData metadata without altering the file.
- **Grid integrity.** Compare CRS, six affine coefficients, pixel dimensions/resolution, dimensions, and bounds as separate mismatch reasons. Return structured compatibility rather than silently aligning. Affine is authoritative; bounds are an envelope. No common analysis resolution is selected. Future resampling concepts distinguish categorical nearest-neighbor policy from continuous bilinear/cubic policy without performing resampling here.
- **Migrations.** Add a numbered migration table and idempotent additive migration. It checks existing columns before adding project fields, creates the new scenes table, and records applied versions. Existing tables and data are not rebuilt. `create_all` remains for first-time setup; migrations run afterward so old installations are evolved explicitly.
- **API shape.** `POST /projects/{id}/scenes` accepts multipart GeoTIFF and explicit sensor plus optional acquisition/product metadata; `GET /projects/{id}/scenes` lists temporal collection; `GET /projects/{id}/scenes/{scene_id}` returns full metadata; `GET /projects/{id}/scenes/{scene_id}/spatial` returns grid/bounds/mask data; `DELETE` removes only that scene. Existing project CRUD is extended additively.
- **Frontend.** Reuse RSAL project selection, dialog, UI primitives, React Query, and toast/error patterns. Add sensor and optional acquisition inputs in the upload flow and a scene table/card list sorted by acquisition. Do not present cross-scene alignment as a capability.

## Risks / Trade-offs

- Legacy project `classes` are generic; adding WBALC defaults must not invalidate existing RSAL projects. Migration backfills WBALC config only where absent and preserves the existing `classes` values.
- Rasterio may expose mask information at dataset and per-band level; tests must verify mask preservation using synthetic masked GeoTIFFs.
- Object storage and database transactions cannot be made atomic. Use upload staging/cleanup for failed DB registration and avoid deleting source data before a committed scene delete.
- The inherited application is much broader than this change; only new scene endpoints and project config should represent multi-temporal support.
- Local filesystem storage is inherited and remains a deployment limitation.

## Migration Plan

1. Clone the inspected RSAL code baseline into WBALC, retaining existing routes and tests.
2. Add OpenSpec requirements and the complete task list before implementation.
3. Add project/domain schemas, Scene model, raster metadata/grid utilities, and numbered additive migration.
4. Add scene service/API, then synthetic raster and migration tests.
5. Add frontend flow and verify typecheck/build/tests.
6. Run backend tests and document exact outcomes. No operation is required on existing user files; migration is additive and scene records start empty.

## Open Questions

None blocking. Whether old RSAL datasets should be explicitly linked to scenes is deferred until reliable sensor/acquisition provenance exists.
