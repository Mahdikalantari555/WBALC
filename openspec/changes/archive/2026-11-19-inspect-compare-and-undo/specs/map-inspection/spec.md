## ADDED Requirements

### Requirement: Inspect native pixel values
The workspace SHALL map an imagery click to the source raster's zero-based row and column and SHALL read the underlying raw band values rather than RGB preview values. It SHALL distinguish missing pixels from numeric zero and identify the source raster being read.

#### Scenario: Inspect missing data
- **WHEN** the operator clicks a pixel marked by a GeoTIFF NoData value or internal validity mask
- **THEN** the probe shows NoData instead of reporting the stored sentinel or masked value

#### Scenario: Inspect a derived preview
- **WHEN** the operator clicks an NDVI or normalized-difference preview
- **THEN** the probe lists the source operands and the computed index when both operands are valid and the denominator is nonzero

### Requirement: Compare dates without moving the viewport
The workspace SHALL allow comparing different dated acquisitions with identical native dimensions, CRS and affine on one map using a keyboard-operable divider. It SHALL NOT implicitly align differing grids or present the preview as a calculated change map.

#### Scenario: Drag the divider across matching scenes
- **WHEN** the operator changes the divider position for two aligned scenes
- **THEN** the visible coverage changes without changing zoom or center and each side is identified by its acquisition date

#### Scenario: Band identities differ
- **WHEN** both scenes are aligned but their declared band order is not the same
- **THEN** each side uses its native default view and the UI states that their band schemas differ
