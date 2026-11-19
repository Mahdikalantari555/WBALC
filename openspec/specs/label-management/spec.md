# label-management Specification

## Purpose
Defines the project contract for label management.

## Requirements

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

### Requirement: Label deletion
The system SHALL delete all label versions for a sample within a project.

#### Scenario: Delete sample labels
- **WHEN** DELETE /projects/{project_id}/labels/{sample_id} for a labeled sample
- **THEN** system returns 204 and no versions of that sample remain in history

#### Scenario: Delete unknown sample
- **WHEN** the sample_id has no labels in the project
- **THEN** system returns 404
