## ADDED Requirements

### Requirement: GeoTIFF upload compatibility
The system SHALL continue to accept legacy GeoTIFF Dataset uploads and return their existing dataset metadata without changing the legacy single-dataset processing contract.

#### Scenario: Existing dataset upload remains available
- **WHEN** a client uploads a GeoTIFF to `POST /projects/{project_id}/upload`
- **THEN** the response SHALL retain the existing Dataset response fields and status semantics.

#### Scenario: Dataset processing is not implicitly multi-scene
- **WHEN** a project contains one or more new Scene records and a legacy Dataset
- **THEN** existing dataset query, labeling, training, and inference operations SHALL remain scoped to their selected/legacy Dataset
- **AND** SHALL NOT infer that a Scene shares its band schema, CRS, dimensions, or affine grid with another scene.

#### Scenario: Preserve stored legacy records during migration
- **WHEN** database migrations are applied to an RSAL-style database
- **THEN** existing Dataset rows and source files SHALL remain unchanged
- **AND** SHALL NOT be auto-converted to Scene rows without reliable sensor/acquisition provenance.
