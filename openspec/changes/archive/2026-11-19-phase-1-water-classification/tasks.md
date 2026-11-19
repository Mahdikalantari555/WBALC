## 1. Audit/spec and compatibility
- [x] 1.1 Audit existing Project classes/config, label validation, checkpoint class order, outputs and UI class display.
- [x] 1.2 Specify canonical taxonomy, crosswalk and binary mappings without conflating reeds with all emergent vegetation.
- [x] 1.3 Decide JSON/versioned config shape and ensure generic legacy projects are distinguishable from WBALC defaults.

## 2. Taxonomy and annotation mapping
- [x] 2.1 Add typed versioned taxonomy/crosswalk validation and explicit project create/update/read behavior.
- [x] 2.2 Resolve label names through the recorded crosswalk; reject unknown/ambiguous labels without mutating submitted history.
- [x] 2.3 Persist immutable taxonomy/class-order snapshots with training runs and checkpoints.

## 3. Products
- [x] 3.1 Retain three-class hard/probability/uncertainty outputs as the source product.
- [x] 3.2 Implement separate binary hard/probability products for both declared interpretations, including masks and geospatial metadata.
- [x] 3.3 Handle absent trained classes explicitly; include source-run/config mapping in export metadata/API response.
- [x] 3.4 Update legends and UI to distinguish internal classes from derived binary interpretation.

## 4. Tests and docs
- [x] 4.1 Add synthetic config/crosswalk/legacy project tests.
- [x] 4.2 Add synthetic raster value tests for both binary mappings, probability sums, nodata and exact pixel/patch grid behavior.
- [x] 4.3 Run backend/frontend checks and document exact results, taxonomy limitations and examples.
