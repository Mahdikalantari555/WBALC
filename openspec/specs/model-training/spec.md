# model-training Specification

## Purpose
Defines training inputs, checkpoint compatibility, and recorded model configuration.

## Requirements

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

### Requirement: Checkpoints are self-describing and validated
A checkpoint SHALL record its format version, model type, class order, band count,
resolution, feature schema, feature count, patch size, stride and iteration. Loading
SHALL validate these fields and the fitted model's class order before use.

#### Scenario: Class order drift
- **WHEN** a checkpoint's stored classes differ from the fitted model's classes
- **THEN** loading fails with an actionable error instead of mislabelling predictions

#### Scenario: Missing field
- **WHEN** a checkpoint lacks a required field such as `bands`
- **THEN** the API returns 409 identifying the field, not 500

#### Scenario: Legacy checkpoint
- **WHEN** a version-1 checkpoint (no feature schema) is loaded
- **THEN** it is treated as a patch-feature checkpoint, flagged as legacy, and never used for pixel inference

### Requirement: Training responses state the configuration used
`POST /train` and `GET /metrics` SHALL report the classification resolution and the
evaluation strategy, and metrics SHALL expose `n_train`, `n_test`, held-out group
counts and per-class IoU.

#### Scenario: Spatial run
- **WHEN** training runs with `evaluation_strategy=spatial` and forms a holdout
- **THEN** metrics report `spatial_holdout`, `n_test`, `held_out_groups` and `per_class_iou`
