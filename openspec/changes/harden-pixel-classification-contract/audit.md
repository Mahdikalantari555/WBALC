# Current WBALC audit for Phase 0

Audit date: 2026-11-18. This is a read-only code/spec review; no code or tests were changed/run for this audit.

## Existing foundations

- `app/services/pipeline.py` extracts one source-pixel feature vector per labeled pixel in explicit `resolution="pixel"` mode; checkpoint v2 records `pixel-band-vector` versus `patch-band-stats`, feature count and band count. RF and LightGBM are supported.
- `app/api/inference.py::_run_inference` honors checkpoint resolution, reads pixel inputs in 256×256 windows, and writes pixel hard/probability/uncertainty exports using the selected Dataset's affine and CRS. `validate_export_grid` reopens and checks output grids.
- `app/services/raster_service.py` uses Rasterio masks/non-finite checks for strict all-band validity. `app/services/inference_service.py` assigns NoData to invalid predictions and avoids categorical interpolation.
- `tests/test_pixel_classification.py` exercises synthetic pixel training/inference, export grid equality, partial region transforms, nodata and a 7×11 rotated-affine/non-square-pixel case. `tests/test_post_merge_stabilization.py` contains additional pixel/grid regression coverage.
- Project study-area geometry and CRS fields exist, and scene records retain sensor-specific metadata. The classifier's Dataset model remains separate from the Scene collection.

## Gaps and constraints relevant to this change

1. `PredictRequest.dataset_id` is optional. Inference falls back to the most recently registered Dataset; callers cannot make the reference raster explicit in every pixel prediction request.
2. Project study-area geometry is stored/validated but not applied as a prediction validity mask. Current validity is based on source raster masks and finite band values.
3. Pixel inference reads windows but accumulates a full `K × H × W` probability cube, a full validity mask, and output maps in memory; it is limited by `max_raster_elements`. This is not out-of-core full-raster processing.
4. Checkpoint v2 records the feature family and count, but the classifier `Dataset` schema does not retain ordered band names/descriptions or sensor/schema identity. A same-count raster with different band meanings/order can therefore pass. Separate `Scene` records retain richer band/sensor metadata but are not connected to classifier training/inference. Legacy checkpoint v1 is accepted as patch-only and has no semantic band identity.
5. Pixel mode is opt-in at the backend training API (default `patch`) and remains API-only in the workspace; the adapter forwards resolution/evaluation options when supplied, but the user-facing learning workspace currently trains patch models. Add an explicit pixel-training control rather than claiming inconsistent defaults.
6. Automated tests assert CRS, transform, bounds, dimensions, nodata and representative values. No evidence was found of a manual QGIS/ArcGIS overlay check, and no 101×73 fixture matching the original example was identified.
7. Existing patch mode is a distinct product. Its cell predictions can be painted into source-grid windows; these must not be described as independent pixel predictions.

## Scope recommendation

Harden the prepared-GeoTIFF pixel inference contract: explicit reference Dataset selection; optional project study-area masking with explicit CRS transformation and no raster resampling; consistent pixel/patch choice across UI/API; fail-fast band feature contract; bounded-memory behavior with an honest documented limit; and synthetic regression plus a manual GIS verification checklist. Keep this change separate from water-specific class recoding, Sentinel preprocessing/fusion, temporal classification, Active Learning redesign, and scientific experiment tracking.
