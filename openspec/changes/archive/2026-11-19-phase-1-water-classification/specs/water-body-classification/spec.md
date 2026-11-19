## ADDED Requirements

### Requirement: Versioned canonical taxonomy
A WBALC-configured classifier MUST use an explicit ordered internal taxonomy and versioned mapping of human-entered labels to model classes. It MUST preserve custom/legacy project taxonomies unless the project is explicitly configured for WBALC classes.

#### Scenario: Canonical project taxonomy
- **WHEN** a WBALC project is created with defaults
- **THEN** its internal classes are ordered `open_water`, `emergent_vegetation`, `land`
- **AND** model, metrics, legends and exports use the same stable class IDs/order

#### Scenario: Explicit alternate label alias
- **WHEN** an annotator submits a label name configured as an alias for an internal class
- **THEN** the training target resolves to that class and both source label name and mapping version remain auditable

#### Scenario: Unknown/ambiguous label name
- **WHEN** a label has no unique configured mapping
- **THEN** it is rejected with an actionable error and is not silently assigned

#### Scenario: Reed terminology
- **WHEN** the project maps `reed` to `emergent_vegetation`
- **THEN** the mapping is explicit project configuration
- **AND** the system does not claim all emergent vegetation is reed

### Requirement: Derived binary water interpretation
The system MUST preserve the internal three-class product and MUST generate a separately identified binary product only under a valid configured interpretation.

#### Scenario: Water versus non-water
- **WHEN** `water_vs_non_water` is selected
- **THEN** open_water and emergent_vegetation map to water, land maps to non-water, and source NoData remains NoData

#### Scenario: Open water versus other
- **WHEN** `open_water_vs_other` is selected
- **THEN** open_water maps to water and emergent_vegetation plus land map to other, with NoData preserved

#### Scenario: Probability recoding
- **WHEN** a binary probability product is requested
- **THEN** probabilities are summed according to the declared mapping
- **AND** remain bounded, retain validity masks and identify their source three-class run

#### Scenario: Required class absent from trained model
- **WHEN** a requested interpretation depends on a class absent from model outputs
- **THEN** binary output is reported unavailable rather than fabricated

### Requirement: Reproducible class semantics
Each training run and classified export MUST record taxonomy/config version, stable class order, label crosswalk and binary interpretation (if applied). Historical records MUST retain the semantics in force when created.

#### Scenario: Configuration changes after training
- **WHEN** project taxonomy or binary interpretation changes
- **THEN** prior run metrics/exports remain associated with their original config snapshot
- **AND** a new model run is required before new classification semantics are presented
