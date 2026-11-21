## MODIFIED Requirements

### Requirement: Queries only propose valid, model-compatible samples
The system SHALL exclude candidates with no valid source pixels from the
candidate pool. The pool granularity SHALL follow the latest checkpoint's
resolution — patch checkpoints rank patch statistics, pixel checkpoints rank
raw per-pixel spectra — unless the request explicitly overrides it via
`sample_resolution`. Uncertainty-based strategies SHALL require a checkpoint
trained at the pool's granularity; a mismatch SHALL fail with an actionable 409
naming both resolutions. Model-free strategies MAY run without a model, in
which case `model_iteration` is null and a note explains the omission. Every
batch SHALL record the granularity it used (`pool.patch_size`, stride and a
note).

#### Scenario: Nodata patches are never suggested
- **WHEN** a scene has a nodata collar and any strategy is queried
- **THEN** no returned sample lies in a patch or pixel without valid values

#### Scenario: Pixel checkpoint with uncertainty
- **WHEN** `strategy=uncertainty` is requested after a pixel-resolution run
- **THEN** the pool is a pixel pool (`pool.patch_size = 1`), candidates carry true per-pixel model probabilities, and the batch note states pixel granularity instead of returning 409

#### Scenario: Pixel checkpoint with diversity
- **WHEN** `strategy=diversity` is requested after a pixel-resolution run
- **THEN** the pool defaults to pixel granularity and the core-set is selected over pixel spectra, with `model_iteration` null and a note explaining no model scores were used

#### Scenario: Explicit granularity override
- **WHEN** a request passes `sample_resolution` that differs from the checkpoint's resolution and asks for model scores
- **THEN** the request fails with a 409 explaining the checkpoint/pool mismatch instead of misusing the model

#### Scenario: Patch checkpoint unchanged
- **WHEN** the latest checkpoint is a patch model and a query is requested without `sample_resolution`
- **THEN** the pool, features and results are identical to the previous patch-grid behaviour

#### Scenario: Already labelled exclusion
- **WHEN** `exclude_labeled=true`
- **THEN** candidates whose resolved sample id is already labelled are still excluded, at either granularity
