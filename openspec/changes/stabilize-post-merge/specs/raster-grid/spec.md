## ADDED Requirements

### Requirement: Exports reproduce the source grid exactly
Every classification GeoTIFF the system writes SHALL have the width, height, CRS,
affine transform, pixel size and bounds of the requested source region. When the
patch grid is clamped at the last row/column, each cell's value SHALL occupy that
cell's true pixel window rather than a uniform stride slot.

#### Scenario: Clamped edge cells
- **WHEN** a 70×70 scene is classified at 8 px patches (last row/column clamped)
- **THEN** the exported hard map is 70×70, its affine equals the source affine, its bounds equal the source bounds, and every cell value lies inside the pixel window recorded for that cell in the `grid` tag

#### Scenario: Region export
- **WHEN** inference is requested for a sub-window `{x0,y0,x1,y1}`
- **THEN** the export dimensions are `x1-x0` by `y1-y0` and its affine equals the source affine translated by `(x0, y0)`

#### Scenario: Gaps are explicit
- **WHEN** `stride` is larger than `patch_size`
- **THEN** pixels covered by no cell are nodata in the export and are not labelled with a class

### Requirement: Export integrity is verified before the artifact is registered
The system SHALL write each export to a temporary file, rename it atomically, and
reopen it to compare dimensions, CRS, affine and bounds with the expected source
window. A failing artifact SHALL be deleted and the request SHALL fail instead of
registering an `Export` row.

#### Scenario: Failed validation
- **WHEN** a written export does not match the expected grid
- **THEN** the partial file is removed and the request returns an error, leaving no download available

### Requirement: Validity masks are consistent across outputs
For any cell the system reports as invalid, the hard value SHALL be the nodata
sentinel, probabilities SHALL be masked, uncertainty SHALL be masked and `valid`
SHALL be false — in JSON responses and in every exported format.

#### Scenario: Nodata collar
- **WHEN** a scene has a fully transparent collar
- **THEN** `valid_map` is false for those cells, `hard_map` is the nodata sentinel, and `probability_map`/`uncertainty_map` are `null` there
