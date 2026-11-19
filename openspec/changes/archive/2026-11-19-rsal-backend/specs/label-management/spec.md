## ADDED Requirements

### Requirement: Submit labels
The system SHALL store human labels as point or polygon geometry with class name and iteration.

#### Scenario: Submit point labels
- **WHEN** POST /projects/{project_id}/labels with point geometry
- **THEN** system stores label with sample_type point

### Requirement: Label correction
The system SHALL support correcting previous labels.

#### Scenario: Correct label
- **WHEN** new label submitted for existing sample and iteration incremented
- **THEN** system stores corrected label version

### Requirement: Label history
The system SHALL keep full history of labels per sample.

#### Scenario: Get label history
- **WHEN** GET /projects/{project_id}/history
- **THEN** system returns all labels for the project
