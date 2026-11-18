## ADDED Requirements
### Requirement: label integrity
The system SHALL reject unknown classes, non-finite geometry coordinates, malformed/unclosed polygon rings, out-of-bounds points, and polygons with no overlap with the selected dataset. Pixel-sample point labels SHALL retain per-pixel identity.

#### Scenario: invalid label
- GIVEN a label outside the raster or with invalid geometry
- WHEN submitted
- THEN it is rejected and no label record is persisted.
