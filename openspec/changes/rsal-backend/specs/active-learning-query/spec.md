## ADDED Requirements

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
