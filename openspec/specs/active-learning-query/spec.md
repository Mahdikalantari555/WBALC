# active-learning-query Specification

## Purpose
Defines the project contract for active learning query.

## Requirements

### Requirement: Query strategies
The system SHALL support uncertainty sampling (least confidence, margin, entropy), diversity/core-set sampling, and hybrid sampling.

#### Scenario: Uncertainty query
- **WHEN** POST /projects/{project_id}/query with strategy uncertainty
- **THEN** system returns batch ordered by uncertainty

#### Scenario: Diversity query
- **WHEN** POST /projects/{project_id}/query with strategy diversity
- **THEN** system returns batch maximizing diversity

#### Scenario: Hybrid query
- **WHEN** POST /projects/{project_id}/query with strategy hybrid
- **THEN** system returns batch combining uncertainty and diversity

### Requirement: Batch query
The system SHALL query a batch of samples, not just one.

#### Scenario: Batch size
- **WHEN** query requests batch_size N
- **THEN** system returns up to N samples

### Requirement: Query response fields
The system SHALL return sample locations/patch coordinates, prediction, confidence, uncertainty, and optional embedding.

#### Scenario: Response fields
- **WHEN** batch is returned
- **THEN** each sample includes coords, prediction, confidence, uncertainty, optional embedding

### Requirement: Queries only propose valid, model-compatible samples
The system SHALL exclude patches with no valid source pixels from the candidate
pool. Uncertainty-based strategies SHALL require a checkpoint trained on patch
features; when the only checkpoint was trained on pixel features the request SHALL
fail with an actionable 409. Model-free strategies MAY run without a model, in which
case `model_iteration` is null and a note explains the omission.

#### Scenario: Nodata patches are never suggested
- **WHEN** a scene has a nodata collar and any strategy is queried
- **THEN** no returned sample lies in a patch without valid pixels

#### Scenario: Pixel checkpoint with uncertainty
- **WHEN** `strategy=uncertainty` is requested after a pixel-resolution run
- **THEN** the response is 409 telling the caller to retrain at patch resolution

#### Scenario: Pixel checkpoint with diversity
- **WHEN** `strategy=diversity` is requested after a pixel-resolution run
- **THEN** the batch is produced from patch embeddings, `model_iteration` is null, and `notes` explains that no model scores were used

#### Scenario: Already labelled exclusion
- **WHEN** `exclude_labeled=true`
- **THEN** patches whose resolved sample id is already labelled are still excluded
