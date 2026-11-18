## Why

WBALC already contains a useful pixel classifier and grid-preserving GeoTIFF export, but its research-critical contract is not fully explicit: pixel inference may silently use the latest Dataset, the stored study area does not constrain predictions, equally sized but semantically different band stacks can pass validation, and windowed reads still accumulate a whole-scene probability cube. Pixel training is API-only while the workspace currently trains patch models. These gaps can make results ambiguous or prevent users from selecting the intended mode even when output CRS and affine appear correct.

## What Changes

- Make the reference Dataset explicit for pixel inference and surface the selected Dataset in the prediction/export provenance.
- Define and apply an optional project study-area mask to pixel predictions and exports without modifying source imagery; validate/transform vector geometry to the raster CRS only, and fail clearly if required CRS information is missing or invalid.
- Establish a fail-fast feature-schema contract for prepared input bands, including band order/identity where metadata is available; never infer semantic equivalence from band count alone.
- Add an explicit pixel-versus-patch control to the workspace and keep API/UI semantics aligned, preserving backwards compatibility for existing patch workflows and patch-only legacy checkpoints.
- Specify bounded-memory processing and truthful size-limit behavior. Do not claim whole-scene inference is out-of-core unless all probability/output paths are actually streamed.
- Expand deterministic synthetic GeoTIFF tests and provide a manual GIS overlay checklist for acceptance evidence.

## Capabilities

### Modified Capabilities
- `pixel-classification`: explicit input identity, feature contract, mask semantics, resolution selection and resource limits.
- `raster-grid`: source immutability, exact-grid exports and independent validation remain mandatory with study-area masking.
- `inference-export`: provenance identifies the input Dataset and whether an optional study-area mask was applied.

## Impact

Backend inference schemas/services and export metadata; Dataset band metadata or a narrowly scoped feature-schema record; project/UI inference selection; synthetic backend/frontend tests; and user documentation. Any persistence change must use an explicit additive migration and preserve existing uploaded files and records.

## Non-goals

No automatic download, preprocessing, reprojection/resampling of imagery, Sentinel-1/2 fusion, temporal model or area-change analysis, water-specific class recoding, active-learning/query-batch redesign, experiment-tracking overhaul, or model-accuracy claims. Do not change legacy patch-grid semantics except to make resolution selection unambiguous. No real imagery or internet is required for tests.
