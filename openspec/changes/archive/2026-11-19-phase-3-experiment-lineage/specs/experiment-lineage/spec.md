## ADDED Requirements

### Requirement: Dataset and scene inputs have immutable content identity
Each newly registered processing input MUST have a content checksum and a metadata/schema snapshot. A TrainingRun MUST reference exact input versions, not only mutable names or project IDs.

#### Scenario: New GeoTIFF registered
- **WHEN** a Dataset or Scene upload is accepted
- **THEN** its original bytes remain unchanged and its SHA-256, size, grid and ordered sensor/band metadata are recorded

#### Scenario: Dataset bytes unavailable or legacy
- **WHEN** existing data lacks a trustworthy registration-time checksum
- **THEN** it is marked legacy/incomplete and not assigned a fabricated content identity

### Requirement: Every training run has a reproducibility manifest
Every new TrainingRun MUST persist an immutable manifest identifying training inputs, label snapshot, taxonomy/feature schema, model configuration, random seed, evaluation/split definition, code revision and dependency lock identity when available.

#### Scenario: Label correction creates a new run
- **WHEN** the effective label version set changes
- **THEN** the new run's label snapshot hash changes and prior run manifest remains unchanged

#### Scenario: Run compared with another run
- **WHEN** a user compares runs
- **THEN** the API exposes metrics alongside differing input hashes, label snapshots, model/config and evaluation protocol
- **AND** it does not compare scores as if inputs were identical when they were not

#### Scenario: Legacy run viewed
- **WHEN** a pre-manifest run is shown
- **THEN** the UI/API identifies unavailable provenance rather than filling unknown fields with guessed values

### Requirement: Experiment groups organize immutable runs
Users MUST be able to create named experiments and associate immutable run records with them without altering the run's manifest or results.

#### Scenario: Run added to an experiment
- **WHEN** a TrainingRun is associated with an Experiment
- **THEN** both identities and the association are durable and queryable
- **AND** the run's original manifest remains unchanged

### Requirement: Artifacts are integrity-checked
New checkpoints and exports MUST have byte checksums recorded after successful atomic creation/validation. Downloads MUST not silently serve an artifact whose checksum fails verification.

#### Scenario: Valid artifact
- **WHEN** a stored artifact matches its recorded checksum
- **THEN** it may be served with its run/input provenance

#### Scenario: Missing or modified artifact
- **WHEN** an artifact is missing or differs from the recorded checksum
- **THEN** serving fails clearly and records/returns an integrity error without replacing the original record

### Requirement: Canonical manifests do not expose secrets or machine-local paths
Manifest hashes MUST use a documented canonical serialization and manifests MUST exclude credentials, tokens and sandbox-specific absolute paths.

#### Scenario: Manifest canonicalized
- **WHEN** equivalent manifest data is serialized
- **THEN** the canonical bytes and resulting hash are stable under key ordering
