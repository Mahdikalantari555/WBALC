## ADDED Requirements

### Requirement: Project creation
The system SHALL allow creating projects with name, classes (list of class names), description, and status.

#### Scenario: Create project successfully
- **WHEN** POST /projects with valid name, classes, description, and status
- **THEN** system returns a project object with generated id and persisted fields

### Requirement: List projects
The system SHALL return all projects.

#### Scenario: List projects
- **WHEN** GET /projects
- **THEN** system returns a list of all projects

### Requirement: Get project
The system SHALL return a single project by id.

#### Scenario: Get existing project
- **WHEN** GET /projects/{project_id} for an existing id
- **THEN** system returns the project

#### Scenario: Get missing project
- **WHEN** GET /projects/{project_id} for a missing id
- **THEN** system returns 404

### Requirement: Update project
The system SHALL allow updating project name, classes, description, and status.

#### Scenario: Update project
- **WHEN** PUT /projects/{project_id} with valid fields
- **THEN** system returns updated project
