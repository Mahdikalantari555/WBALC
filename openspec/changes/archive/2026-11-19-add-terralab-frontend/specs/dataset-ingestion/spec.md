## ADDED Requirements

### Requirement: Raw dataset file access
The system SHALL serve the original uploaded GeoTIFF bytes so clients can
render bands and composites.

#### Scenario: Download original file
- **WHEN** GET /projects/{project_id}/dataset/{dataset_id}/file for an existing dataset
- **THEN** system returns the original GeoTIFF with image/tiff content type

#### Scenario: Missing dataset file
- **WHEN** the dataset id is unknown or the file is gone from storage
- **THEN** system returns 404

### Requirement: Extended dataset metadata
The system SHALL include file size and patch-grid information in dataset
metadata responses.

#### Scenario: Metadata fields
- **WHEN** dataset metadata is returned (upload, list, or get)
- **THEN** it includes size_bytes and patch_grid (patch_size, stride, rows, cols, total_patches)

### Requirement: Dataset deletion
The system SHALL delete a dataset, its stored file, its labels and its exports.

#### Scenario: Delete dataset
- **WHEN** DELETE /projects/{project_id}/dataset/{dataset_id} for an existing dataset
- **THEN** system returns 204 and the dataset, file, labels and exports are removed

#### Scenario: Delete missing dataset
- **WHEN** the dataset id is unknown in the project
- **THEN** system returns 404
