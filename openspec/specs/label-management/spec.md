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

### Requirement: Reverse the current label without deleting history
Active Learning SHALL let an operator undo their most recent successful submission in the current review view. The backend SHALL only undo the requested version if it is still current in that project, keep its withdrawal timestamp in history and export, and exclude withdrawn versions from current labels and future training. Existing model runs SHALL remain unchanged.

#### Scenario: Undo a first submission
- **WHEN** an operator undoes the only retained label linked to a query item
- **THEN** the item returns to pending and the withdrawn version remains visible in the audit history

#### Scenario: Undo a revision
- **WHEN** an operator undoes a revision of a label
- **THEN** the previous retained version becomes current, with the corresponding prior decision restored for the same item when available

#### Scenario: Undo a superseded version
- **WHEN** a newer current label already exists or the requested version has been withdrawn
- **THEN** the API rejects the operation without changing the current label
