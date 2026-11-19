# Phase 1 audit — Water-body classification

Audit date: 2026-11-18. Read-only review; no code/tests changed or run.

## Existing foundation
- `Project` has generic `classes` plus `classification_config`; new-project defaults currently define `open_water`, `emergent_vegetation`, `land`, and a binary interpretation setting.
- RF/LightGBM supervised training consumes `project.classes`; labels are validated against that generic class list.
- Exports preserve model class indices and include class tags/palette. No evaluated water-specific recoding path was identified.
- Dataset ingestion records band count and basic grid metadata. Separate Scene ingestion records ordered band names/descriptions/dtypes and Sentinel-1/2 metadata, but Scene data is not connected to training/inference.

## Gaps
- The config is not yet an end-to-end classifier contract: class meaning, label mapping, default selection/UI, model labels and outputs can diverge.
- `binary_output_interpretation` is stored but not used to produce a binary classified raster/probability/area product.
- No explicit controlled alias/crosswalk exists for domain terms such as “reed”; emergent vegetation must not automatically be claimed to equal reeds.
- No water-area metrics (deferred to Phase 4), domain-specific class evaluation protocol, or sensor-aware prepared-input contract exists.

## Phase boundary
Phase 1 defines taxonomic/configuration and classification output semantics for one prepared raster. It does not add time-series processing, area-change analysis, sensor fusion, preprocessing, or automatic class inference.
