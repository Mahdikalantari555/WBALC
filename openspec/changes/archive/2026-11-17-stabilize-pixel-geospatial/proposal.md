## Why
The current supervised classifier trains on patch summaries and predicts one class per patch cell. Its output is therefore not source-pixel classification, while the project needs an explicitly correct pixel-resolution option and exact geospatial output guarantees before WBALC specialization.

## What Changes
- Retain existing patch-grid endpoints as the backward-compatible default and introduce an explicit pixel-resolution supervised mode.

**Proposal stage completed.** This proposal records intended scope; implementation begins below and may mark any item not verifiably completed as deferred rather than archive it as complete.
- Add exact grid validation and pixel-grid hard/probability/uncertainty output paths; prohibit categorical interpolation.
- Preserve native raster-window aspect ratio in the right-side sample-review preview; contain rather than stretch rectangular samples.
- Improve raster masks, edge coverage, and processing behavior; record limitations where whole-array processing remains.
- Add spatially independent evaluation as an explicit training option with per-class precision/recall/F1/IoU and confusion matrix. Mark in-sample metrics as training metrics.
- Validate labels against dataset bounds and known classes; reject malformed geometries and document coordinate-space semantics.
- Add value- and metadata-based raster tests and archive this change only after verification.

## Capabilities
### New capabilities
- `pixel-classification`: explicit pixel feature model contract and source-grid predictions.
- `raster-grid`: exact reference-grid validation and categorical output integrity.
- `evaluation`: spatially independent holdout and truthful metric labeling.
- `label-integrity`: validation of label geometries, mapping, and raster bounds.
### Modified capabilities
- `model-training`, `inference-export`, `dataset-ingestion`, `label-management`.

## Impact
Backend services and schemas, raster API behavior only when the new explicit mode is selected, tests, README, and license/attribution documentation. Existing patch mode remains default. No water-specific behavior is introduced.
