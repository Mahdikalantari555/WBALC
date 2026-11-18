## ADDED Requirements

### Requirement: Minimal study and scene workspace
The frontend SHALL expose project selection/creation and project-scoped GeoTIFF scene upload and inspection using the existing WBALC/RSAL design system.

#### Scenario: Create or select a study
- **WHEN** a user creates or selects a project
- **THEN** the workspace SHALL associate subsequent scene operations with that project.

#### Scenario: Upload with sensor and acquisition metadata
- **WHEN** a user uploads a GeoTIFF scene
- **THEN** the UI SHALL require a Sentinel-1 or Sentinel-2 sensor selection
- **AND** SHALL permit acquisition date/time and product metadata to be entered when not inferable.

#### Scenario: Review temporal scene collection
- **WHEN** scenes exist for a project
- **THEN** the UI SHALL make acquisition ordering apparent
- **AND** SHALL display date (including an explicit unknown state), sensor, band count, CRS, spatial resolution, and raster dimensions.

#### Scenario: Validation feedback
- **WHEN** the API or client detects incomplete or invalid upload metadata
- **THEN** the UI SHALL show a clear actionable validation message and SHALL not claim the scene was registered.
