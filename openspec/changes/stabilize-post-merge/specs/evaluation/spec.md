## MODIFIED Requirements

### Requirement: In-sample metrics are never presented as validation
Metrics computed on the training data SHALL be labelled `insufficient_train_metrics`
with an `evaluation_warning` explaining why an independent holdout was unavailable.
Spatial groups SHALL be described as source-pixel blocks, not as a guarantee of
spatial independence.

#### Scenario: Too few spatial groups
- **WHEN** spatial evaluation is requested and fewer than three groups or no two-class holdout can be formed
- **THEN** metrics report the in-sample fallback, the reason, and the strategy that was requested

#### Scenario: Random holdout reproducibility
- **WHEN** the same labels are trained twice with the same seed and strategy
- **THEN** the reported metrics are identical and the seed is included in the response

#### Scenario: Absent class
- **WHEN** a class has zero support in the evaluation subset
- **THEN** its metrics are reported with `support: 0` and the evaluation limitation is visible in the response
