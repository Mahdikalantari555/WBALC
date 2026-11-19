# frontend-spec-alignment Specification

## Purpose
Defines the project contract for frontend spec alignment.

## Requirements

### Requirement: Prediction resolution is explicit in the workspace
Every training and prediction request the workspace submits MUST carry an explicit
resolution and validation protocol, and every displayed score MUST show the
resolution, protocol and sample counts recorded for that run. The workspace MUST
NOT rely on an implicit engine default for either field.

#### Scenario: Operator trains a model
- **WHEN** the operator submits the training panel
- **THEN** the adapter sends an explicit `resolution` and `evaluation_strategy`
- **AND** the returned run's recorded values are displayed with its metrics

#### Scenario: Unknown resolution or protocol
- **WHEN** a training request names a resolution or protocol outside the allowed set
- **THEN** the adapter rejects it with a 400 before contacting the engine
- **AND** no run is created

#### Scenario: Patch versus pixel wording
- **WHEN** a field or run is patch-based
- **THEN** the workspace describes it as one value per patch cell and does not call it a per-pixel classification
- **AND** a pixel-based field is described as one value per source pixel

### Requirement: Scores are qualified, never bare
The workspace MUST distinguish an independent held-out score from an in-sample
fit, and a spatially grouped holdout from a random one, wherever a score is shown
or exported.

#### Scenario: Insufficient held-out data
- **WHEN** the engine records an `insufficient_train*` evaluation
- **THEN** the overview, arena, metrics caption and evaluation protocol panel identify the numbers as in-sample
- **AND** the JSON and CSV exports record the same caveat

#### Scenario: Random holdout
- **WHEN** a run's recorded protocol is `random`
- **THEN** the workspace states that neighbouring patches were split randomly and the score is optimistic
- **AND** it points to the spatial holdout for reporting

### Requirement: Run comparison states its differences
When two runs are compared, the workspace MUST list the recorded fields that
differ and MUST NOT present their scores as a like-for-like comparison.

#### Scenario: Runs differ in protocol or resolution
- **WHEN** the compared runs record different resolutions, protocols, sample counts, model families, taxonomies or scoring applicability
- **THEN** the arena lists those differing fields
- **AND** it does not claim the inputs were identical

### Requirement: Unimplemented engine capabilities are stated, not simulated
Where a capability exists only as project configuration or spec text and the
engine does not implement it, the workspace MUST say so rather than render an
implied product.

#### Scenario: Binary interpretation configured
- **WHEN** a project records a binary output interpretation
- **THEN** the workspace displays it with a note that this engine version does not emit a separate binary product

#### Scenario: Study area configured
- **WHEN** a project has study-area geometry
- **THEN** the map states that prediction masks come from source-raster validity only

#### Scenario: Raster drawn in pixel space
- **WHEN** a dataset cannot be placed on the geographic map
- **THEN** the workspace explains why in the active language, from the adapter reason code

### Requirement: Derived counts are per record
Counts derived from label lists MUST de-duplicate by sample identity so that a
corrected label does not count twice.

#### Scenario: Label corrected
- **WHEN** a sample's class is corrected, producing a new label version
- **THEN** the evaluation label distribution still counts that sample once

#### Scenario: No collaboration claim
- **WHEN** the review queue is displayed
- **THEN** the workspace does not present users, permissions or shared state
- **AND** it describes the queue as stored in this browser
