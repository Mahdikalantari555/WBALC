## ADDED Requirements

### Requirement: Single pixel-to-display transform
The frontend SHALL compute every sample position (thumbnail crop, map marker,
map footprint, submitted label geometry) from one shared transform module, with
no CSS-only or duplicated coordinate arithmetic.

#### Scenario: Shared maths on both sides of the BFF
- **WHEN** the adapter converts a sample's pixel coordinates for the browser and the map places a marker for the same sample
- **THEN** both calls resolve to the same transform implementation and produce identical display coordinates

#### Scenario: Round trip is lossless
- **WHEN** a display coordinate is converted to pixel space and back (and the reverse)
- **THEN** the original coordinate is recovered within 1e-6 relative tolerance for the dataset's transform

### Requirement: Review thumbnail is the actual patch
The review panel SHALL render the sample's patch by reading exactly the patch's
pixel window from the sample's own dataset, not by positioning a scaled copy of
the whole raster.

#### Scenario: Thumbnail shows the classified patch
- **WHEN** a query sample with pixel window `x0..x1, y0..y1` is selected in the review panel
- **THEN** the thumbnail is rendered from a GeoTIFF read of exactly that window of that dataset, in the same band mode as the map

#### Scenario: Thumbnail and marker agree at the scene edge
- **WHEN** the selected sample is in the first or last grid row/column of the scene
- **THEN** the thumbnail crop and the map footprint describe the same ground rectangle, including the edge-clamped patch

#### Scenario: Thumbnail uses the sample's dataset
- **WHEN** the project has several datasets and the reviewed sample belongs to a dataset other than the one currently shown on the map
- **THEN** the thumbnail is read from the sample's dataset and the panel indicates which dataset the sample belongs to

#### Scenario: Sample without a patch footprint
- **WHEN** a sample's position cannot be resolved to a patch window (for example an imported polygon label)
- **THEN** the thumbnail shows a centred one-patch window and the panel states that no patch footprint exists, instead of fabricating one

### Requirement: Map layers are scoped to the active dataset
The map SHALL draw only the samples and drafts that belong to the dataset
currently displayed.

#### Scenario: No cross-scene markers
- **WHEN** the map shows dataset A while the queue contains samples of dataset B
- **THEN** dataset B's samples are not drawn on the map, and are still reviewable in the panel

#### Scenario: Drawn drafts inherit their dataset
- **WHEN** the user draws a sample on dataset A and later switches the map to dataset B
- **THEN** that draft is not drawn on dataset B and is submitted against dataset A

### Requirement: Visible patch footprints
Every sample SHALL carry a display-space footprint derived from the backend patch
grid, and the map SHALL show the footprint of the selected sample and of hovered
samples.

#### Scenario: Footprint matches the grid
- **WHEN** a sample is selected
- **THEN** the map draws its patch rectangle at the position and size the backend grid assigns to that patch

#### Scenario: Saved labels keep their footprint
- **WHEN** a labeled sample is reloaded from the backend
- **THEN** it is returned with its pixel window and footprint, so a corrected label lines up with its thumbnail

### Requirement: Honest georeferencing state
The map SHALL detect datasets whose georeferencing cannot be rendered faithfully
as an axis-aligned overlay (rotated transform, unsupported CRS, or strongly
non-axis-aligned reprojected extent), display the dataset in pixel space, and
tell the user why.

#### Scenario: Rotated transform
- **WHEN** a dataset transform has non-zero rotation terms
- **THEN** the map uses pixel-space presentation and shows a warning naming the reason

#### Scenario: Unsupported CRS
- **WHEN** the dataset CRS cannot be resolved to a projection definition
- **THEN** the map uses pixel-space presentation and shows a warning naming the reason

#### Scenario: Supported north-up scene is unchanged
- **WHEN** the dataset is a north-up UTM scene with a resolvable CRS
- **THEN** the map keeps the WGS84 basemap presentation and no warning is shown

### Requirement: Thumbnail performance
The system SHALL avoid re-fetching and re-rendering the full raster for each
thumbnail.

#### Scenario: Windowed read with a cached handle
- **WHEN** the review panel renders thumbnails for successive samples of the same dataset
- **THEN** the source GeoTIFF is fetched and parsed at most once per dataset, and each thumbnail costs a windowed read of the patch pixels

## MODIFIED Requirements

### Requirement: Dataset management on real rasters
The system SHALL upload GeoTIFFs to RSAL, list them with real metadata, render
band combinations client-side from the original bytes, and delete datasets.

#### Scenario: Upload and render
- **WHEN** the user uploads a multi-band GeoTIFF
- **THEN** the dataset appears with RSAL-extracted metadata and the map renders RGB/false-color/NDVI from the actual file

#### Scenario: Non-georeferenced raster
- **WHEN** the dataset has no usable CRS/bounds
- **THEN** the map falls back to pixel-space display, labeling still works, and the pixel-space mode is stated in the map

#### Scenario: Delete dataset
- **WHEN** the user deletes a dataset
- **THEN** the adapter calls RSAL dataset deletion and the dataset disappears from the list
