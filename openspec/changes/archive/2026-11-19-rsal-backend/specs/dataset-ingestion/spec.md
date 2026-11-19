## ADDED Requirements

### Requirement: GeoTIFF upload
The system SHALL accept GeoTIFF uploads for a project and extract CRS, transform, shape, bands, dtype.

#### Scenario: Upload GeoTIFF
- **WHEN** POST /projects/{project_id}/upload with a GeoTIFF file
- **THEN** system stores the file and returns dataset metadata

### Requirement: Multi-band imagery support
The system SHALL support multi-band satellite imagery metadata.

#### Scenario: Multi-band metadata
- **WHEN** dataset has multiple bands
- **THEN** metadata includes bands count greater than 1

### Requirement: Dataset listing
The system SHALL list datasets for a project with metadata.

#### Scenario: List datasets
- **WHEN** GET /projects/{project_id}/dataset
- **THEN** system returns dataset metadata list
