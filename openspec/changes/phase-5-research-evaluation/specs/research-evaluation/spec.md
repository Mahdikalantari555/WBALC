## ADDED Requirements

### Requirement: Evaluation protocols are explicit, leakage-safe and reproducible
Every research evaluation MUST identify its split strategy, grouping unit, seed, exact train/test membership and exclusions. Temporal evaluation MUST hold out whole acquisition groups; spatial evaluation MUST document block and buffer settings. Insufficient independent data MUST be reported rather than replaced with in-sample scores.

#### Scenario: Temporal holdout
- **WHEN** temporal generalization is evaluated
- **THEN** all samples from held-out acquisition groups are absent from training, tuning and query ranking
- **AND** split membership and dates are recorded

#### Scenario: Spatial buffered holdout
- **WHEN** spatial evaluation is selected
- **THEN** groups are separated according to declared block/buffer configuration and the CRS/units are recorded
- **AND** train/test group overlap is zero

#### Scenario: Insufficient independent groups
- **WHEN** data cannot support the selected independent split
- **THEN** evaluation is `insufficient` with a reason and no training-set metric is labeled test performance

### Requirement: Metrics preserve class identity and undefined states
Evaluation results MUST include stable class order and per-class metrics/support, and MUST represent undefined metrics as undefined with a reason rather than as a perfect score.

#### Scenario: Class missing from held-out reference
- **WHEN** a class has no support in a test split
- **THEN** its support is zero and undefined metrics are null/reasoned
- **AND** the report does not imply successful validation for that class

### Requirement: Active-learning comparisons are controlled
Comparisons of query strategies MUST use matched seeds/initial labels, candidate eligibility, evaluation partitions and stopping rules, and MUST include a seeded random baseline.

#### Scenario: Strategy comparison
- **WHEN** two or more strategies are compared
- **THEN** the plan/run bundle records shared and differing factors and source query batches
- **AND** results are not presented as paired if their evaluation inputs are not matched

### Requirement: Uncertainty and area metrics require independent evidence
Probability calibration/coverage MUST use held-out reference labels. Water-area error MUST require an independent reference area and documented measurement method.

#### Scenario: No independent area reference
- **WHEN** area outputs exist without ground-truth area
- **THEN** mapped area is reported as an estimate only and no area-error metric is generated

#### Scenario: Held-out uncertainty assessment
- **WHEN** uncertainty quality is evaluated
- **THEN** the report states held-out sample count, calibration/coverage method and thresholds

### Requirement: Research report bundles are reproducible and qualified
A research report bundle MUST be generated from immutable Phase 3/4 records and include data/model/config hashes, protocol/split details, metrics, software context and limitations in machine-readable and human-readable formats.

#### Scenario: Report generated
- **WHEN** a complete research plan has results
- **THEN** JSON/CSV and Markdown/HTML artifacts identify every included/excluded run and the artifact checksums
- **AND** the report can be regenerated from stored records

#### Scenario: External validation absent
- **WHEN** no independent real-data validation has been recorded
- **THEN** the application states that software evaluation passed but scientific validity is not established
