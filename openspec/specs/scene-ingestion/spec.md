# scene-ingestion Specification

## Purpose
Defines how dated scenes are registered, validated, and stored independently.

## Requirements

### Requirement: Register independent scenes
The system SHALL register any number of GeoTIFF scenes independently under a project, with nullable acquisition time and sensor-specific metadata.

#### Scenario: Register scenes from both sensors
- **WHEN** a project receives Sentinel-1 and Sentinel-2 uploads
- **THEN** each scene SHALL retain its own sensor, bands, raster metadata, source reference, and sensor-specific fields
- **AND** neither scene SHALL inherit metadata from another scene.

#### Scenario: Temporal collection with missing/duplicate dates
- **WHEN** a project has scenes with known, duplicate, and missing acquisition times
- **THEN** listing SHALL order known acquisitions chronologically newest-first with deterministic ties
- **AND** SHALL include undated scenes after dated scenes without inventing dates.

#### Scenario: GeoTIFF validation and metadata response
- **WHEN** a client uploads a readable GeoTIFF under an existing project
- **THEN** the API SHALL validate it and return complete metadata including platform/sensor, source name/storage reference, CRS, affine, bounds, dimensions, pixel dimensions/resolution, bands, band names/descriptions, dtypes, NoData and mask availability, plus upload and registration timestamps.

#### Scenario: Invalid or unreadable upload
- **WHEN** the uploaded content is not a supported readable GeoTIFF or exceeds configured upload limits
- **THEN** the API SHALL return a clear client error
- **AND** SHALL leave no scene row or partial stored source.

#### Scenario: Optional acquisition metadata
- **WHEN** acquisition date, product level, or optional sensor metadata is unavailable
- **THEN** the scene SHALL still register with those fields null and retain required sensor identity.

#### Scenario: Preserve source and validity information
- **WHEN** ingestion succeeds for a raster containing NoData and/or a GDAL validity mask
- **THEN** the stored source bytes SHALL remain unchanged
- **AND** the scene metadata SHALL report NoData and mask availability without flattening or discarding the source validity mask.

#### Scenario: Scene detail and spatial metadata
- **WHEN** a client requests scene detail or spatial metadata
- **THEN** it SHALL receive the registered scene's complete metadata or its CRS/transform/bounds/dimensions/resolution/grid summary, respectively.

#### Scenario: Isolated deletion
- **WHEN** a client deletes a scene belonging to a project
- **THEN** only that scene's row and source file SHALL be removed
- **AND** the project and its other scenes SHALL remain.
