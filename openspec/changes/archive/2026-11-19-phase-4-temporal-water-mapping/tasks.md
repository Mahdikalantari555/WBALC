## 1. Audit/spec
- [x] 1.1 Audit Scene ingestion, metadata/grid comparison and Dataset-only processing.
- [x] 1.2 Define native-grid scene classification, area math, explicit alignment and late-fusion boundaries.

## 2. Scene classification
- [x] 2.1 Add immutable Scene analysis-run model/API and explicit compatible model/schema selection.
- [x] 2.2 Classify one Scene at a time on native grid with source mask, taxonomy and Phase 3 lineage.
- [x] 2.3 Add scene class/probability/uncertainty exports with reopened grid validation and source immutability checks.

## 3. Area and temporal analysis
- [x] 3.1 Implement projected-affine and geographic-geodesic pixel area with units and synthetic numerical tests.
- [x] 3.2 Add per-date per-class/binary water area, valid coverage and documented study-area inclusion rule.
- [x] 3.3 Add temporal series and class-transition/change summaries; exclude nodata and expose denominators.
- [x] 3.4 Reject mismatched grids by default; add explicit target-grid categorical alignment operation and provenance if implemented.

## 4. Sensor comparison/fusion
- [x] 4.1 Add controlled late-fusion request with explicit target grid, inputs, rule, weights and missing-data semantics.
- [x] 4.2 Preserve per-sensor results and reject implicit raw-band early fusion/harmonization.
- [x] 4.3 Compare single-sensor and fused output lineage in the experiment UI.

## 5. Frontend, tests, verification
- [x] 5.1 Add temporal scene result browser/map and native-versus-derived grid indicators.
- [x] 5.2 Add synthetic tests for projected/geodesic area, nodata, class transitions, sensor schema mismatch and explicit alignment.
- [x] 5.3 Run backend/frontend suites and document exact outcomes; no real-data claims without external reference validation.
