## Decisions

### Evaluation protocols and leakage controls
- Define protocol records: random stratified sample split, spatial grouped/buffered split, and temporal acquisition/scene holdout. Each run stores exact train/test label/sample IDs or a deterministic split manifest/hash, random seed, grouping key, exclusions and rationale.
- Temporal holdout groups all observations from the same acquisition/scene together. Spatial protocol uses configurable block size and buffer distance in pixel/map units with explicit CRS requirements; do not treat adjacent pixels or same-scene labels as independent.
- If required independent groups/classes are insufficient, return `insufficient` plus reason; do not substitute training metrics and call them validation. Any fallback is explicit and separately labeled.
- Keep test/validation labels out of fitting, query ranking, preprocessing fit, threshold tuning and model selection. Persist protocol role and enforce no identifier overlap at service level.

### Metrics
- Report class-order-stable confusion matrix, per-class precision/recall/F1/IoU/support, macro/weighted summaries and balanced accuracy, with undefined metrics represented as null plus reason (not perfect scores).
- Probability quality is reported only for held-out samples and includes declared calibration metric(s) and calibration sample counts. Coverage/abstention curves identify the uncertainty threshold and retained coverage.
- Area error is reported only when an independently supplied reference-area/label source and its method are identified; include absolute/signed error and units. Do not use model's own mapped area as its truth.
- Aggregate across scenes/regions with scene-level distributions and confidence intervals/resampling unit declared; never pool all pixels and obscure scene-level variation.

### Research plans and comparisons
- A research plan declares factors, levels, repetitions/seeds, holdout protocol, compute/resource limits and comparison metric before runs. Ablations differ in named factors; all other manifest fields are compared and differences exposed.
- Random AL baseline uses Phase 2 durable seeded batches. Comparisons use matched initial labels, same candidate eligibility, same evaluation split and repeat seeds where feasible.
- Sensor/fusion comparisons use Phase 4 lineage and explicit grids; no raw sensor equivalence is assumed.

### Report bundle
- Produce portable JSON/CSV and Markdown/HTML summary with experiment/run/input/checkpoint/artifact hashes, protocol/split IDs, metrics, class mappings, area units, resource/software versions and explicit caveats.
- Reports are generated from immutable records, are regenerable, and state missing inputs/provenance and limitations. No citation or performance claim is generated automatically.

### Test data and external validity
- Unit/integration tests use synthetic fixtures only and verify split disjointness, metric calculations, stable ordering, report schemas and deterministic repeatability.
- Real-data scientific validation is an operator-run acceptance gate that requires user-provided independent reference data. Software completion may be declared separately from scientific validation; status must be prominent.

## Verification
Test known synthetic labels for all metrics, group/time split disjointness, no leakage, insufficient-data cases, report reproducibility and area-error calculations. Test migrations and API/UI paths. Do not fetch external imagery or depend on internet.
