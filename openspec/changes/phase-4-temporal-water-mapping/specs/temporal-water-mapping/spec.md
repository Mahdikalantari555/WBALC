## ADDED Requirements

### Requirement: Every Scene can be classified independently on its native grid
A Scene classification MUST identify the Scene, model and compatible feature schema and MUST preserve that Scene's native grid. Classification MUST NOT assume scenes share band order, resolution, CRS or alignment.

#### Scenario: Compatible Scene
- **WHEN** a model schema explicitly matches the selected Scene
- **THEN** classification is produced on its native CRS, affine, dimensions and validity mask with run provenance

#### Scenario: Same-band-count incompatible sensor
- **WHEN** Sentinel-1 and Sentinel-2 or differently ordered bands have equal counts but incompatible declared schemas
- **THEN** classification is rejected unless a compatible explicit schema/model is selected

### Requirement: Water-area estimates are physically meaningful and qualified
Area calculations MUST account for affine geometry and CRS units, retain masks, identify taxonomy and report valid coverage and method.

#### Scenario: Projected CRS
- **WHEN** a classified pixel grid uses a projected CRS with supported linear units
- **THEN** pixel area is computed from the affine determinant and converted to square metres

#### Scenario: Geographic CRS
- **WHEN** the grid uses geographic coordinates
- **THEN** pixel footprint area is computed geodesically from pixel corners, not from degree-squared values

#### Scenario: Study-area boundary
- **WHEN** an area result uses center-in-polygon masking
- **THEN** that inclusion rule and its boundary approximation are recorded

#### Scenario: Invalid coverage
- **WHEN** one or more pixels are nodata/masked
- **THEN** class area uses only valid pixels and reports the valid denominator/coverage

### Requirement: Temporal change requires validated grid and class semantics
Direct change analysis MUST require matching grids, taxonomy/class meanings and validity definitions. Mismatches MUST fail closed or use an explicit alignment operation.

#### Scenario: Identical native grids
- **WHEN** selected scene classifications have matching grids and semantics
- **THEN** transition counts, area changes and valid coverage are computed with NoData excluded

#### Scenario: Unlike grids
- **WHEN** source classifications have different CRS, affine, shape or extent
- **THEN** direct comparison fails with structured mismatch details
- **AND** the system does not treat them as aligned

#### Scenario: Explicit categorical alignment
- **WHEN** the user explicitly selects a reference grid and requests alignment
- **THEN** the derivative uses nearest-neighbor categorical resampling, records the operation and target grid, and leaves all native sources unchanged

### Requirement: Sensor fusion is explicit late fusion
Any Sentinel-1/2 fusion MUST combine explicitly selected derived products under a declared rule and target grid; it MUST retain per-sensor outputs and provenance.

#### Scenario: Fusion requested without compatible products
- **WHEN** source products, schemas, grids or required configuration are incompatible or missing
- **THEN** fusion is unavailable with a clear reason

#### Scenario: Reproducible fusion
- **WHEN** a valid fusion experiment runs
- **THEN** its source runs, target grid/alignment, rule, weights, masks and output checksum are persisted
- **AND** original per-sensor results remain accessible

### Requirement: Temporal products preserve lineage
Scene classifications, area summaries, change products and fusion outputs MUST be immutable analysis records linked to source scenes, model/config versions and exact grid/mask semantics.
