## ADDED Requirements

### Requirement: Training hands off to the classification map
When a training run succeeds, the workspace SHALL make the fresh classification
visible immediately: it SHALL enable the classification layer, navigate to the
map view when the operator is elsewhere, and load the new run's field without
requiring a manual refresh.

#### Scenario: Train from the learning page
- **WHEN** the operator trains successfully from the active-learning page
- **THEN** the workspace navigates to the map, the classification layer is on, and the field painted comes from the run that just finished

#### Scenario: Train from the map view
- **WHEN** a run finishes while the operator is already on the map
- **THEN** the painted field is replaced by the new run's field without navigation or refresh

### Requirement: Active-learning context map with a target marker
The active-learning review SHALL include a map of the sample's own dataset with
its classification field, one pin per proposed sample coloured by predicted
class, and a distinct target marker dropped exactly on the focused sample's
pixel/cell; focusing a sample SHALL zoom the map to the target, and clicking a
pin SHALL focus that sample so the panel's change/delete/reject actions act on
it.

#### Scenario: Overview before judgement
- **WHEN** the analyst focuses a proposed sample
- **THEN** the context map shows the scene-wide classification for orientation before zooming

#### Scenario: Zoom to the target
- **WHEN** a sample is focused (list navigation, keyboard or pin click)
- **THEN** the map animates to the sample and a marker marks the exact target pixel/cell, distinguishable from the other proposal pins

#### Scenario: Manage a sample from the map
- **WHEN** the analyst clicks a proposal pin
- **THEN** that sample becomes the focused one and the existing change-label, delete, reject and defer actions apply to it

#### Scenario: Pixel sample thumbnail keeps context
- **WHEN** a proposed sample is a single pixel (window area ≤ 2 px)
- **THEN** the thumbnail renders a clamped context window (±32 px) around it instead of a 1-pixel image, and the meta line says "pixel"

#### Scenario: Sample placement is grid-honest
- **WHEN** a sample is shown on any map from the review flow
- **THEN** its position/highlight uses the sample's recorded pixel window, never pool row/col reinterpreted against a different field grid

### Requirement: Deterministic default dataset
The workspace SHALL default the active dataset to the project's upload (training
raster) dataset — the latest dataset with `origin='upload'` — rather than the
most recently registered dataset row, so the identity panel and training target
are the raster the operator intends.

#### Scenario: Fresh project load
- **WHEN** a project whose scenes were registered after the training raster is opened
- **THEN** the active dataset is the training raster, not the newest scene dataset

#### Scenario: Upload-only fallback
- **WHEN** a project has no `origin='upload'` dataset rows
- **THEN** the first dataset is selected and the UI still functions
