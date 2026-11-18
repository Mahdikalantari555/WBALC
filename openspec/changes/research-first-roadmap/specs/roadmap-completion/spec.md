## ADDED Requirements

### Requirement: End-to-end outputs retain complete lineage
Every classified, area, temporal-change, fusion and evaluation output MUST be traceable through reference Scene/Dataset bytes, feature schema, label/taxonomy versions, query batches where relevant, training run/checkpoint, evaluation protocol and output checksum.

#### Scenario: Trace an exported time-series result
- **WHEN** a user opens any published temporal/report artifact
- **THEN** the system can identify its source scenes/grids, class mapping, model/runs, masks/alignment operations, software/config and integrity hash

#### Scenario: Legacy artifact lacks lineage
- **WHEN** historical records predate lineage support
- **THEN** unavailable provenance is identified as incomplete, never backfilled with guessed facts

### Requirement: Native data and grid compatibility remain explicit across phases
The system MUST preserve original imagery and native grid facts across ingestion, training and analysis. It MUST reject unlike-grid operations unless the user invokes a separately recorded alignment operation with an explicit target grid and suitable resampling semantics.

#### Scenario: Inputs are compatible
- **WHEN** an operation requires direct pixel comparison
- **THEN** all required CRS/affine/dimension/class-schema checks pass and are reported

#### Scenario: Inputs are unlike
- **WHEN** required grids or schemas differ
- **THEN** the operation stops or requests an explicit compatible derived operation; it never silently treats inputs as aligned

### Requirement: Phase completion is evidence-based
A phase MUST NOT be marked complete until its requirements, migration/API/UI tests, integration tests and documentation are satisfied. Historical test results or unperformed manual checks MUST NOT be represented as current verification.

#### Scenario: Phase verification
- **WHEN** all phase tasks are implemented
- **THEN** exact test/build commands and outcomes are recorded for the current source state
- **AND** incomplete manual/external validation gates remain explicitly pending

### Requirement: Software completion is distinct from scientific validation
The application MUST distinguish implemented/reproducible software behavior from externally established scientific performance.

#### Scenario: No independent field/reference data
- **WHEN** the full synthetic software acceptance suite passes but independent reference evaluation has not been supplied
- **THEN** project status may be software-complete but scientific validation remains not established
- **AND** the UI/report MUST state this distinction

### Requirement: Full synthetic end-to-end path is executable offline
A deterministic test path MUST exercise the complete chain from synthetic immutable GeoTIFFs, through labeling/query/training and scene analysis, to evaluation/report output without internet or real satellite data.
