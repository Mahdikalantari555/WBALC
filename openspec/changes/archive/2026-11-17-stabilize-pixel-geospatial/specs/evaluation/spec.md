## ADDED Requirements
### Requirement: truthful evaluation
The system SHALL label evaluation mode, SHALL report per-class precision, recall, F1, IoU and confusion matrix, and SHALL distinguish independent holdout metrics from in-sample metrics. The system SHOULD support spatially grouped holdout and SHALL report when independent evaluation is insufficient.

#### Scenario: spatial blocks
- GIVEN samples assigned to spatial groups
- WHEN spatial evaluation is selected
- THEN no group occurs in both training and holdout sets.

#### Scenario: insufficient spatial data
- GIVEN too few distinct blocks or inadequate class coverage
- WHEN spatial evaluation is requested
- THEN in-sample metrics are explicitly labeled as such and independent evaluation is stated unavailable.
