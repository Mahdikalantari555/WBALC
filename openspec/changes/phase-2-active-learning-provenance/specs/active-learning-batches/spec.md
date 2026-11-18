## ADDED Requirements

### Requirement: Query selections are durable records
Every successful active-learning query MUST persist a batch record and its selected items with enough context to explain and reproduce the selection. The batch MUST identify its project, selected Dataset, strategy implementation/version, parameters, seed, grid, candidate count and ordered eligible-candidate-set hash, and model/training run when applicable.

#### Scenario: Query completes
- **WHEN** a query succeeds with zero or more items
- **THEN** a durable batch and ordered item records are created atomically
- **AND** the response returns batch identity and recorded selection context

#### Scenario: Query fails
- **WHEN** candidate generation or strategy selection fails
- **THEN** no partial batch is visible

#### Scenario: Batch history is reopened
- **WHEN** the user opens a prior batch from another session/browser
- **THEN** the same item identities, order, selection rationale and recorded decision states are returned
- **AND** the application does not pretend locally unsaved drafts were submitted

### Requirement: Sampling strategies share a valid candidate pool
Every strategy MUST sample from the same declared pool of valid, eligible, unlabeled candidates unless the request explicitly opts into labeled candidates. Invalid/nodata items MUST never be selected.

#### Scenario: Seeded random sampling
- **WHEN** a random query is submitted with a seed and unchanged candidate pool
- **THEN** selection is without replacement and repeatable
- **AND** the seed and pool size are persisted

#### Scenario: Existing deterministic strategies
- **WHEN** uncertainty, diversity, hybrid or SOM selection is run
- **THEN** it uses the same eligibility rules and records its method/model context

### Requirement: Annotation decisions are durable and auditable
A query item MUST support pending, labeled, rejected and deferred states. Submitting or correcting a label from an item MUST link that label version to the item where the association is known, while preserving immutable label history.

#### Scenario: Label accepted
- **WHEN** an annotator submits a label for a selected query item
- **THEN** the item becomes labeled and references the persisted label version

#### Scenario: Suggestion rejected or deferred
- **WHEN** the annotator rejects or defers a suggestion
- **THEN** that decision and time are persisted and visible when the batch is resumed

#### Scenario: Existing labels have no batch
- **WHEN** a legacy label has no associated query item
- **THEN** it remains valid and its provenance is reported as manual/legacy/unknown rather than fabricated

### Requirement: Sampling history does not imply collaboration
Batch history MUST be project-scoped and MUST NOT present annotator identity, permissions or shared collaboration features unless an authentication/authorization capability is separately implemented.

#### Scenario: No configured identity system
- **WHEN** batches are reviewed in the current application
- **THEN** optional operator notes may be stored, but the UI makes no authenticated-user or access-control claim
