# Phase 4 audit — Temporal water mapping

Audit date: 2026-11-18. Read-only review; no code/tests changed or run.

## Existing foundation
- Project-scoped Scene registration supports independent Sentinel-1 and Sentinel-2 acquisitions, acquisition times, sensor-specific metadata and native CRS/affine/dimensions/resolution/band/mask metadata.
- Grid comparison utilities report native grid differences without aligning imagery.
- Existing `Dataset` training/inference/AL services process one Dataset and do not consume Scene collection records.
- Project study area and canonical water-class configuration are present, but not applied as temporal classification/area products.

## Gaps
- No per-Scene trained classification execution or outputs; no Scene-to-Dataset conversion/linkage contract.
- No per-date class-area estimate, uncertainty-aware area output, time-series summary or change detection.
- No explicit common-grid alignment workflow for comparing differently gridded outputs.
- No sensor-specific model registry or controlled Sentinel-1/Sentinel-2 fusion experiment.

## Phase boundary
Phase 4 turns registered scenes into independently classified, provenance-linked dated products and explicit temporal area/change analyses. Native sources remain immutable. Unlike grids fail by default; any categorical alignment requires an explicit reference grid and recorded nearest-neighbor operation. Sensor fusion is a controlled experiment over compatible derived products, not implicit raw-band concatenation.
