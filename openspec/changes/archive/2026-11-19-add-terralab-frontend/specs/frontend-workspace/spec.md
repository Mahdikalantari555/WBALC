## ADDED Requirements

### Requirement: TerraLab workspace shell
The system SHALL provide a single-page workspace in `frontend/` using the
TerraLab design (sidebar, topbar, projects/datasets/learning/analytics views)
with all data served by the RSAL backend.

#### Scenario: Workspace loads real projects
- **WHEN** the user opens the workspace with RSAL running
- **THEN** the sidebar and project dashboard list the projects from RSAL with derived stats (iteration, accuracy, labeled count)

#### Scenario: Backend unavailable
- **WHEN** RSAL is unreachable
- **THEN** the UI shows an actionable connection error and never fabricates demo data

### Requirement: RSAL-only data path
The system SHALL route every browser API call through a server-side adapter to
RSAL (`RSAL_API_URL`); no local database, ORM, or simulated training remains.

#### Scenario: Real training
- **WHEN** the user triggers training from the UI
- **THEN** the adapter calls RSAL POST /train and the displayed metrics come from the RSAL response

### Requirement: Project creation with classes
The system SHALL create RSAL projects from the workspace, mapping class names
to RSAL `classes: string[]` and assigning display colors deterministically.

#### Scenario: Create project
- **WHEN** the user submits name, description and class names
- **THEN** a RSAL project is created and appears in the sidebar with colored class chips

### Requirement: Dataset management on real rasters
The system SHALL upload GeoTIFFs to RSAL, list them with real metadata, render
band combinations client-side from the original bytes, and delete datasets.

#### Scenario: Upload and render
- **WHEN** the user uploads a multi-band GeoTIFF
- **THEN** the dataset appears with RSAL-extracted metadata and the map renders RGB/false-color/NDVI from the actual file

#### Scenario: Non-georeferenced raster
- **WHEN** the dataset has no usable CRS/bounds
- **THEN** the map falls back to pixel-space display and labeling still works

#### Scenario: Delete dataset
- **WHEN** the user deletes a dataset
- **THEN** the adapter calls RSAL dataset deletion and the dataset disappears from the list

### Requirement: Active learning review loop
The system SHALL query RSAL for batches (uncertainty methods, diversity,
hybrid), keep the pending queue in per-project client state, and submit
reviewed labels to RSAL.

#### Scenario: Cold start
- **WHEN** no model exists and the user requests a batch
- **THEN** the UI offers diversity sampling and returns a real RSAL diversity batch

#### Scenario: Review and submit
- **WHEN** the user labels samples (mouse or keyboard shortcuts 1-9, enter to submit, s to skip, arrows to navigate) and submits
- **THEN** labels are stored in RSAL with geometry and the queue advances; skips stay local

#### Scenario: Queue persistence
- **WHEN** the user reloads the page mid-review
- **THEN** the pending batch and drafts are restored from client storage

### Requirement: Label import
The system SHALL import labels from GeoJSON or CSV with class-name mapping,
converting geometries to dataset pixel space before submitting to RSAL.

#### Scenario: Import GeoJSON
- **WHEN** the user imports a GeoJSON file whose features carry a class property
- **THEN** valid features become RSAL labels and the result reports imported/skipped counts

### Requirement: Label correction and deletion
The system SHALL let users correct labels (new RSAL version) and delete a
sample's labels via the RSAL deletion endpoint.

#### Scenario: Correct label
- **WHEN** the user changes the class of a labeled sample
- **THEN** RSAL stores a new version and history reflects both

#### Scenario: Delete label
- **WHEN** the user deletes a labeled sample
- **THEN** all its versions are removed from RSAL and the UI updates

### Requirement: Real analytics with CSV export
The system SHALL display learning curve, confusion matrix and per-class metrics
from RSAL training runs, class distribution from current labels, and export
iteration metrics as CSV. No simulated metrics are shown.

#### Scenario: Analytics after training
- **WHEN** at least one RSAL training run exists
- **THEN** analytics shows the real curve/confusion/per-class data

#### Scenario: Export CSV
- **WHEN** the user exports analytics
- **THEN** a CSV of real iteration metrics downloads

### Requirement: Donor source removal
The change SHALL delete both donor frontend folders after verification.

#### Scenario: Cleanup
- **WHEN** the frontend is verified against RSAL
- **THEN** `satellite-active-learning-frontend/` and `satellite-image-classification-frontend/` no longer exist in the tree
