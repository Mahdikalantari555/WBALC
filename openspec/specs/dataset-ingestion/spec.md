# dataset-ingestion Specification

## Purpose
Defines the project contract for dataset ingestion.

## Requirements

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
