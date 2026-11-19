# study-projects Specification

## Purpose
Defines study-level configuration, classification semantics, and compatibility.

## Requirements

### Requirement: WBALC study configuration
The system SHALL represent a study project with name, description, optional study-area geometry, optional study-area CRS, classification configuration, and creation/update timestamps.

#### Scenario: Create WBALC project defaults
- **WHEN** a client creates a project without supplying classification configuration
- **THEN** the project SHALL retain the internal classes `open_water`, `emergent_vegetation`, and `land`
- **AND** it SHALL use a documented binary interpretation default without removing those internal classes.

#### Scenario: Configure binary interpretation
- **WHEN** a client selects a supported binary interpretation
- **THEN** the project SHALL preserve the three internal class definitions
- **AND** SHALL persist the binary interpretation independently.

#### Scenario: Invalid classification configuration
- **WHEN** a request omits a required internal class, duplicates a class, or selects an unsupported binary interpretation
- **THEN** the API SHALL return a validation error without changing the project.

#### Scenario: Existing project compatibility
- **WHEN** an existing project record is migrated
- **THEN** its existing classes, name, description, status, and timestamps SHALL be preserved.
