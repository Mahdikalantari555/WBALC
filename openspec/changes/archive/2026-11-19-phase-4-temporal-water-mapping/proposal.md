## Why

WBALC can register a time-ordered collection of Sentinel scenes but its classifier still operates only on legacy Datasets. Without scene-level predictions and area/change outputs, the project is a scene library rather than a temporal water-monitoring system. This phase connects the existing scene model to reproducible classification and time-series analysis while preserving each scene's native grid and distinct sensor schema.

## What Changes
- Add explicit per-Scene classification using compatible, provenance-tracked model/feature schemas and native-grid outputs.
- Derive per-class and water-area estimates with pixel-area method, valid coverage and uncertainty summaries, clipped/defined by study area.
- Add date-series summaries and change maps/statistics between selected acquisitions.
- Require exact grid compatibility for direct comparison; provide only explicit alignment to a user-selected reference grid with categorical nearest-neighbor resampling and full provenance.
- Add controlled late-fusion experiments over per-scene classifications from Sentinel-1/2, with user-declared fusion rule/weights and complete source lineage; no raw-band fusion by default.
- Add temporal collection UI for date selection, map comparison and per-date results.

## Capabilities
### New: `scene-classification`, `water-area-estimation`, `temporal-change-analysis`, `sensor-fusion-experiments`
### Modified: `scene-library`, `inference-export`, `experiment-management`.

## Impact
Scene APIs/services, model/input schema selection, classification/export records, area/change computation, explicit alignment/fusion configuration and temporal UI. Additive persistence migrations only. Synthetic tests; real research outputs require user-supplied labels/data.

## Non-goals
No automated imagery discovery/download, atmospheric/SAR preprocessing, radiometric normalization, hidden grid harmonization, hard-coded 10/20 m analysis scale, forecasting, or scientific conclusions without reference data.
