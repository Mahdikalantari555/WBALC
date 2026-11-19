## ADDED Requirements

### Requirement: Label deletion
The system SHALL delete all label versions for a sample within a project.

#### Scenario: Delete sample labels
- **WHEN** DELETE /projects/{project_id}/labels/{sample_id} for a labeled sample
- **THEN** system returns 204 and no versions of that sample remain in history

#### Scenario: Delete unknown sample
- **WHEN** the sample_id has no labels in the project
- **THEN** system returns 404
