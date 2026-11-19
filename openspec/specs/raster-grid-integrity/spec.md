# raster-grid-integrity Specification

## Purpose
Defines the project contract for raster grid integrity.

## Requirements

### Requirement: Preserve and describe native raster grids
The system SHALL preserve native source CRS, affine transform, pixel dimensions, raster dimensions, and spatial bounds per scene and SHALL NOT silently reproject, resample, or treat distinct scene grids as aligned.

#### Scenario: Same native grid
- **WHEN** two scenes share CRS, affine transform, pixel size, dimensions, and bounds within documented numeric tolerance
- **THEN** grid comparison SHALL report them as compatible.

#### Scenario: Different grid characteristics
- **WHEN** scenes differ in CRS, pixel size, affine origin, dimensions, or spatial extent
- **THEN** comparison SHALL identify each applicable difference explicitly
- **AND** SHALL not resample either raster.

#### Scenario: Rotated/skewed affine grid
- **WHEN** a raster has nonzero affine rotation/shear terms
- **THEN** the original six affine coefficients SHALL remain authoritative and unchanged.

#### Scenario: Resampling policy concepts
- **WHEN** future processing selects a resampling strategy
- **THEN** categorical and continuous raster policies SHALL remain distinguishable
- **AND** this foundation SHALL not choose a universal target resolution or execute resampling.
