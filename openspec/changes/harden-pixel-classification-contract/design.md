## Context

The archived `stabilize-pixel-geospatial` change delivered explicit pixel features, mask-aware predictions, exact-grid exports, and synthetic tests. This proposal closes the remaining Phase 0 contract gaps without replacing that work or conflating it with the separate multi-temporal Scene foundation. See `audit.md` for the inspected code paths and current limitations.

## Goals / Non-goals

**Goals:** unambiguous inference input identity; consistent pixel/patch selection; optional study-area masking; explicit input feature compatibility; honest resource bounds; stable geospatial export guarantees and verification.

**Non-goals:** preprocessing or aligning imagery; scene-level temporal processing; changing classifier algorithms or evaluating accuracy gains; turning patch-cell output into pixel predictions; broad experiment or annotation redesign.

## Decisions

### Reference input and provenance

Every pixel prediction/export request must resolve one explicit project-owned Dataset. Prefer making `dataset_id` required in the public pixel request and frontend; if compatibility requires retaining the old request shape, the compatibility route must resolve and return the exact Dataset ID and emit a deprecation path rather than silently representing the latest Dataset as user-selected. Exports and response metadata must identify the reference Dataset, training run, resolution and applied-mask status. Dataset ownership must be validated before opening any file.

### Resolution compatibility

The training resolution stored in a checkpoint is authoritative for inference. Add a visible workspace control and submit the chosen training resolution explicitly; current workspace behavior remains patch until the user selects pixel. Omitted resolution behavior stays backward-compatible and documented at each public API boundary; legacy v1 checkpoints remain patch-only. Do not silently reinterpret existing models or patch outputs.

### Study-area geometry

When a project has no study-area geometry, source raster validity alone determines valid predictions. When one is configured, pixel predictions are valid only where (a) all required source bands are valid and finite and (b) the pixel center lies inside the study-area geometry. Transform the vector geometry from its declared project CRS into the selected raster CRS using a coordinate-operation library; this is vector coordinate transformation, not raster reprojection. Reject missing CRS, invalid transformation, or unusable geometry with a clear client error. Preserve NoData outside either mask in hard, probability and uncertainty products. Do not edit the source raster. Patch behavior remains unchanged unless a separate, explicit compatible implementation is specified and tested; do not imply a patch mask was applied when it was not.

### Prepared-input feature schema

A band-count equality check is insufficient to prove features have the same meaning or order. Define a stable, serializable feature-schema identity for every Dataset and checkpoint, including ordered band descriptions/names and an explicit user-provided schema/sensor identity when names are absent. New training must verify all contributing Datasets share the same declared schema before combining samples; new checkpoints record it. Inference compares it with the selected input. If compatibility cannot be proven, fail closed unless the caller explicitly confirms use of an unverified schema; record that override in run/inference/export provenance and surface it in the UI. This applies to existing v2 checkpoints too: `pixel-band-vector` and band count identify feature shape, not semantic band identity. The legacy v1 format remains patch-only but likewise lacks semantic identity. Never infer that Sentinel-1 and Sentinel-2 bands are interchangeable. No resampling, band synthesis, normalization, or sensor harmonization is introduced here. Extend Dataset metadata additively only as needed; do not infer missing band meanings from filenames or sensor defaults.

### Memory and outputs

The accepted implementation may retain the current configured raster-element limit if it is surfaced consistently before expensive processing and documented. If removing whole-scene probability arrays, all response/export/map consumers must be accounted for and output parity tested; do not stream one path while another silently retains the full cube and then claim out-of-core processing. Any implementation that still materializes full arrays must state that limitation and reject over-limit inputs before allocation. All generated rasters must retain exact dimensions, CRS, affine, bounds and NoData semantics relative to the selected reference window, and be reopened/validated before publication.

### Compatibility and migration

Source GeoTIFF bytes remain immutable. Existing Dataset, Scene, label, checkpoint and export records/files must remain readable. Any new persisted band metadata uses a numbered, explicit, idempotent additive migration; do not rebuild tables or backfill guessed band semantics. Unknown legacy feature schemas must be marked unknown and handled through a documented compatibility policy, not fabricated metadata.

### Verification

Use synthetic in-memory GeoTIFF fixtures only. Cover multi-Dataset selection, same-count reordered/different-name bands, missing CRS, study polygon inside/outside and CRS transformation, nodata conjunction, pixel/patch resolution compatibility, partial windows, rotated/non-square affine, and reopened hard/probability/uncertainty output metadata and values. Add a documented manual QGIS overlay procedure; only mark it verified when a human has actually performed and recorded it. The original 101×73 case should be included as an additional synthetic regression, not as a substitute for the existing 7×11 rotated/NoData edge case.

## Risks / Trade-offs

- Tightening input selection or band checks could surprise users of old checkpoints; preserve legacy behavior where possible and make uncertainty explicit.
- CRS transformation of polygons depends on available coordinate-operation grids; tests must use deterministic local CRS transforms and report unavailable operations without network access.
- Study-area geometry validity currently has basic schema validation; full topology repair is out of scope. Invalid geometry must fail rather than be silently repaired.
- A truly streaming probability export could require a broader response/API redesign. It is acceptable to preserve a strict limit in this change, but not to overstate scalability.
- Browser overlays may have separate display CRS behavior; native GeoTIFF export correctness remains independently testable.

## Migration Plan

1. Complete this proposal/spec/task plan before implementation.
2. Implement schema/API and compatibility behavior with additive migration only if required.
3. Add synthetic test fixtures and exercise service, API, and UI paths.
4. Run focused and full suites; record exact results and limitations.
5. Perform and record the manual GIS overlay check before claiming that acceptance criterion complete.

## Resolved Decisions

- **Checkpoint without semantic band identity (including current v2):** fail closed unless the caller explicitly confirms use of an unverified schema; persist/display that override in provenance. This preserves a deliberate compatibility path without presenting feature-family/band-count equality as scientific validation.
- **Frontend reference Dataset:** default the visible selector to the currently displayed raster when one exists, but always submit its Dataset ID explicitly for pixel prediction. There is no hidden “latest Dataset” fallback in the pixel UI path.
