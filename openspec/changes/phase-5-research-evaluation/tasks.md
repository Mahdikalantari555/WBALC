## 1. Audit/spec
- [x] 1.1 Audit current random/spatial metrics, splits, charts, missing temporal protocols and reference-data constraints.
- [x] 1.2 Define leakage controls, research metrics, random-baseline comparison and qualified report bundle.

## 2. Protocol/split engine
- [ ] 2.1 Add immutable evaluation protocol and split membership records with deterministic hashes.
- [ ] 2.2 Implement temporal scene/acquisition holdout with no leakage into training, tuning or AL candidate ranking.
- [ ] 2.3 Implement spatial grouped/buffered holdout with explicit units/CRS, configurable blocks and insufficiency states.
- [ ] 2.4 Preserve and accurately label random stratified and existing spatial evaluation semantics.

## 3. Research metrics and comparisons
- [ ] 3.1 Add null/reason semantics for undefined class metrics; balanced accuracy and stable per-class support.
- [ ] 3.2 Add held-out calibration/uncertainty coverage metrics with sample counts and thresholds.
- [ ] 3.3 Add independent reference-area evaluation and signed/absolute area errors; prohibit self-reference.
- [ ] 3.4 Add research plans/ablations and matched-seed Active Learning comparisons with Phase 2 random batches.
- [ ] 3.5 Aggregate per-scene/region distributions with declared resampling units; avoid pixel pseudoreplication.

## 4. Reporting/UI
- [ ] 4.1 Generate checksum-linked JSON, CSV and Markdown/HTML report bundles from Phase 3/4 manifests.
- [ ] 4.2 Add UI for protocol definition, run comparison, split details, results export and scientific-validation status.
- [ ] 4.3 Include resource/time constraints and incomplete provenance in reports; do not create unsupported claims.

## 5. Verification and final acceptance
- [ ] 5.1 Add synthetic tests for all metrics, temporal/spatial disjointness, leakage, insufficient data and deterministic reports.
- [ ] 5.2 Verify report/API/UI integration with Phases 0–4 and migrations from an existing DB.
- [ ] 5.3 Run full backend/frontend suites, build, static checks and documented manual GIS checks; record actual results.
- [ ] 5.4 Provide a user-supplied independent reference-data validation procedure and record status separately from software acceptance.
