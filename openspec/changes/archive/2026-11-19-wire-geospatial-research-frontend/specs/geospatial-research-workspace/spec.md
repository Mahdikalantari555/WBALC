# Spec Delta

## Purpose

Provide a second, research-oriented frontend example (SvelteKit) that runs entirely against the real WBALC (RSAL) engine, offering six research views with real data, an offline Leaflet map and client-persisted review state.

## ADDED Requirements

### Requirement: RSAL-only data path for the example app
The example app SHALL source all displayed data from the RSAL backend through a server-side adapter; no hardcoded observations, samples, models, metrics or predictions remain.

#### Scenario: No mock data
- **WHEN** the example app is built for production
- **THEN** no module under `src/lib/data/` contains static research datasets or simulated metrics

#### Scenario: Backend unavailable
- **WHEN** RSAL is unreachable
- **THEN** the UI shows an actionable connection error and never fabricates demo data

### Requirement: Server-side adapter (BFF)
The example app SHALL proxy every browser API call to RSAL via SvelteKit server route handlers using `RSAL_API_URL`, translating RSAL view models to app view models.

#### Scenario: Project list
- **WHEN** the overview or workspace loads
- **THEN** projects are fetched from RSAL through the adapter and displayed with derived stats

#### Scenario: Raster bytes
- **WHEN** a map view needs imagery
- **THEN** original GeoTIFF bytes are fetched through the adapter file endpoint and rendered client-side

### Requirement: Six research views on real data
The example app SHALL provide overview, geospatial workspace, temporal analysis, active learning, model arena, and results & evaluation views populated from RSAL projects, scenes/datasets, labels, query results, training runs and metrics.

#### Scenario: Overview loads
- **WHEN** the user opens the app
- **THEN** the overview shows project status and a water-area series derived from RSAL scenes (or an empty state if unavailable)

#### Scenario: Temporal analysis
- **WHEN** the user selects dates
- **THEN** acquisition metadata comes from RSAL scenes and the comparison reflects real scene pairs

#### Scenario: Model arena
- **WHEN** at least one training run exists
- **THEN** model metrics and confusion data come from RSAL metrics

#### Scenario: Results & evaluation
- **WHEN** the user filters by model and class
- **THEN** confusion counts and per-class metrics come from RSAL metrics

### Requirement: Offline map with band modes and pixel fallback
The example app SHALL render the Leaflet map from real raster bytes with RGB/false-color/NDVI/custom band modes, and fall back to pixel space for non-georeferenced rasters.

#### Scenario: Georeferenced raster
- **WHEN** the dataset has a usable CRS and bounds
- **THEN** the map overlays the raster in WGS84 with working pan/zoom and layer toggles

#### Scenario: Non-georeferenced raster
- **WHEN** the dataset has no usable CRS/bounds
- **THEN** the map uses pixel space (CRS.Simple) and labeling still works

### Requirement: Active learning review loop on real data
The example app SHALL query RSAL for batches, keep the pending queue and drafts in per-project client state, submit reviewed labels to RSAL, and support keyboard shortcuts (class keys 1-9, Enter submit, S skip, arrows navigate).

#### Scenario: Cold start
- **WHEN** no model exists and a batch is requested
- **THEN** the UI offers diversity sampling and returns a real RSAL diversity batch

#### Scenario: Review and submit
- **WHEN** the user labels samples and submits
- **THEN** labels are stored in RSAL with geometry and the queue advances; skips stay local

#### Scenario: Queue persistence
- **WHEN** the user reloads mid-review
- **THEN** the pending batch and drafts are restored from client storage

### Requirement: Label import, correction and deletion
The example app SHALL import labels from GeoJSON/CSV with class mapping and reprojection, allow correction (new RSAL version) and deletion via RSAL endpoints.

#### Scenario: Import GeoJSON
- **WHEN** the user imports a GeoJSON file with a class property
- **THEN** valid features become RSAL labels and the result reports imported/skipped counts

#### Scenario: Delete label
- **WHEN** the user deletes a labeled sample
- **THEN** all its versions are removed from RSAL and the UI updates

### Requirement: Real analytics with CSV export
The example app SHALL display learning curve, confusion matrix and per-class metrics from RSAL training runs, class distribution from current labels, and export iteration metrics as CSV; no simulated metrics are shown.

#### Scenario: Analytics after training
- **WHEN** at least one RSAL training run exists
- **THEN** analytics shows real curve/confusion/per-class data

#### Scenario: Export CSV
- **WHEN** the user exports analytics
- **THEN** a CSV of real iteration metrics downloads

### Requirement: Example app packaging and docs
The example app SHALL be documented in its own README and referenced from the root README, with environment variables documented, and remain optional (not a default compose service).

#### Scenario: Documentation
- **WHEN** a developer clones the repo
- **THEN** the example README explains how to run it against RSAL and lists required env vars
