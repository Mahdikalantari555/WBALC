## ADDED Requirements

### Requirement: Classical models
The system SHALL support Random Forest and LightGBM training.

#### Scenario: Train classical model
- **WHEN** POST /projects/{project_id}/train with model_type rf or lightgbm
- **THEN** system trains model and stores checkpoint

### Requirement: Training triggered by labels
The system SHALL trigger training after new labels are submitted.

#### Scenario: Training after labels
- **WHEN** labels submitted and training invoked
- **THEN** system uses current labeled data

### Requirement: Checkpoints
The system SHALL save model checkpoints per iteration.

#### Scenario: Checkpoint saved
- **WHEN** training completes for iteration
- **THEN** checkpoint artifact is stored

### Requirement: Metrics
The system SHALL calculate overall accuracy, F1 macro/weighted, confusion matrix, per-class metrics.

#### Scenario: Metrics stored
- **WHEN** GET /projects/{project_id}/metrics
- **THEN** system returns accuracy, f1_macro, f1_weighted, confusion_matrix, per_class
