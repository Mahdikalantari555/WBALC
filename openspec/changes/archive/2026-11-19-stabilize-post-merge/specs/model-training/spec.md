## ADDED Requirements

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
