## ADDED Requirements

### Requirement: Inference
The system SHALL run inference on whole image or specific regions.

#### Scenario: Predict
- **WHEN** POST /projects/{project_id}/predict with optional region
- **THEN** system returns predictions

### Requirement: Probability and hard maps
The system SHALL return probability maps and hard classification maps.

#### Scenario: Map outputs
- **WHEN** inference runs
- **THEN** system returns probability and hard class maps

### Requirement: GeoTIFF export
The system SHALL export results as GeoTIFF.

#### Scenario: Export GeoTIFF
- **WHEN** GET /projects/{project_id}/download/{type} with export type
- **THEN** system returns GeoTIFF result
