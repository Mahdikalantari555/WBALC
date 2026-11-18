## ADDED Requirements

### Requirement: Native input rasters remain immutable and unaligned
The system MUST retain uploaded source GeoTIFF bytes unchanged. It MUST NOT silently reproject, resample, interpolate, overwrite, or align input imagery as part of pixel classification. Vector study-area coordinates MAY be transformed for masking, but this MUST NOT change the raster grid or source pixels.

#### Scenario: Pixel inference uses a native reference grid
- **WHEN** pixel inference is run on a prepared GeoTIFF
- **THEN** the output grid is derived from that exact Dataset or requested source window
- **AND** no input raster alignment operation is performed

#### Scenario: Unlike grids or band stacks are supplied
- **WHEN** a selected input is incompatible with the model feature schema or a multi-input operation requires unlike grids
- **THEN** the system reports the incompatibility
- **AND** does not treat the inputs as aligned or perform an implicit resampling

### Requirement: Exact geospatial outputs are verified before publication
Every pixel export MUST be checked against the selected reference grid for width, height, CRS, affine transform and bounds, and MUST preserve the combined validity mask. Categorical values MUST NOT be interpolated. A failed verification MUST prevent the export from being published.

#### Scenario: Verified export
- **WHEN** an output passes reopened-grid and validity checks
- **THEN** it may be published with provenance identifying its reference Dataset, run, resolution and applied-mask status

#### Scenario: Failed export
- **WHEN** a grid or validity check fails
- **THEN** the output artifact is removed or kept unavailable and a clear failure is returned
