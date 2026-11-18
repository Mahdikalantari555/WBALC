## ADDED Requirements
### Requirement: raster grid compatibility
The system SHALL compare dimensions, CRS, affine transform, pixel size, and bounds before treating rasters as grid-aligned. Categorical output SHALL use integer class values and a reserved NoData value. The system SHALL NOT use bilinear or cubic resampling for categorical rasters.

#### Scenario: incompatible grids
- GIVEN rasters whose dimensions, CRS, transform, or bounds differ
- WHEN compatibility is checked
- THEN validation fails with a specific error.

#### Scenario: source-grid pixel output
- GIVEN pixel inference for a reference raster
- WHEN its GeoTIFF is reopened
- THEN width, height, CRS, transform, bounds, and NoData agree with the corresponding reference window.
