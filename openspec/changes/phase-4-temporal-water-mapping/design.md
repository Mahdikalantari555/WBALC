## Decisions

### Scene classification and sensor schema
- Scene remains independent from legacy Dataset unless an explicit immutable processing-input record references the Scene. Do not copy or rewrite source data to force domain equivalence.
- Each Scene classification names the input Scene, model/checkpoint, ordered feature schema, taxonomy version and native output grid. A model may run only if required sensor/band schema is explicitly compatible; same band count alone is insufficient.
- Maintain sensor-specific workflows. Sentinel-1 and Sentinel-2 are never merged as raw bands by default. A prepared, user-defined feature schema may enable compatible model inference.

### Area estimates
- Use the output's exact affine and CRS. For projected CRSs, compute pixel footprint area from the affine determinant and convert declared linear units to square metres. For geographic CRSs, calculate geodesic pixel polygon area from transformed pixel corners; do not use degrees-squared as area.
- Report valid-pixel coverage, included class counts, area in square metres and square kilometres, mask/study-area rule, area method and uncertainty summary. If study-area boundaries are applied by pixel-center inclusion, label that approximation explicitly. No claim of subpixel boundary precision.
- Separate per-class area from binary water interpretation; link both to the same internal three-class output and config version.

### Temporal comparison and alignment
- Direct change comparison requires identical dimensions, CRS, affine transform, class semantics and validity/mask contract. Otherwise fail with a structured mismatch report.
- Optional alignment is a separate explicit operation. User selects the target/reference grid and area of interest; only categorical output maps use nearest-neighbor. The operation records source/target grid fingerprints, method, mask behavior and software version. Never alter source Scenes or represent aligned derivatives as native data. No default analysis resolution.
- Change statistics distinguish observed class transitions from invalid/unobserved pixels. Report denominator/coverage per date; do not count nodata as land or no-change.

### Sensor fusion
- Phase 4 supports experimental late fusion of already-classified, compatible products only. The experiment must declare sources, target grid/alignment operation, fusion rule, weights/threshold and missing-data behavior. Retain original per-sensor products alongside fused output.
- Early fusion of raw Sentinel-1/2 bands, calibration, speckle/cloud preprocessing and compositing are out of scope until a separately specified sensor preprocessing contract exists.

### Persistence and UI
- Store scene classification, area result, temporal comparison and fusion as immutable analysis-run records linked to Phase 3 manifests and source scene/checkpoint/export hashes.
- UI shows date, sensor, native grid, alignment state and coverage; never hides a non-native derivative or mismatched grid.

## Verification
Use small synthetic multi-date/multi-sensor GeoTIFFs with known class patterns, differing grids/CRSs, masks, rotated affine and known areas. Test fail-closed grid mismatch, explicit alignment semantics, geodesic/projected area calculations, temporal transition accounting, schema mismatch and lineage. No real satellite imagery or internet required.
