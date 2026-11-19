## 1. Audit/spec
- [x] 1.1 Audit current random/spatial metrics, splits, charts, missing temporal protocols and reference-data constraints.
- [x] 1.2 Define leakage controls, research metrics, random-baseline comparison and qualified report bundle.

## 2. Protocol/split engine
- [x] 2.1 Add immutable evaluation protocol and split membership records with deterministic hashes.
- [x] 2.2 Implement temporal scene/acquisition holdout with no leakage into training, tuning or AL candidate ranking.
- [x] 2.3 Implement spatial grouped/buffered holdout with explicit units/CRS, configurable blocks and insufficiency states.
- [x] 2.4 Preserve and accurately label random stratified and existing spatial evaluation semantics.

## 3. Research metrics and comparisons
- [x] 3.1 Add null/reason semantics for undefined class metrics; balanced accuracy and stable per-class support.
- [x] 3.2 Add held-out calibration/uncertainty coverage metrics with sample counts and thresholds.
- [x] 3.3 Add independent reference-area evaluation and signed/absolute area errors; prohibit self-reference.
- [x] 3.4 Add research plans/ablations and matched-seed Active Learning comparisons with Phase 2 random batches.
- [x] 3.5 Aggregate per-scene/region distributions with declared resampling units; avoid pixel pseudoreplication.

## 4. Reporting/UI
- [x] 4.1 Generate checksum-linked JSON, CSV and Markdown/HTML report bundles from Phase 3/4 manifests.
- [x] 4.2 Add UI for protocol definition, run comparison, split details, results export and scientific-validation status.
- [x] 4.3 Include resource/time constraints and incomplete provenance in reports; do not create unsupported claims.

## 5. Verification and final acceptance
- [x] 5.1 Add synthetic tests for all metrics, temporal/spatial disjointness, leakage, insufficient data and deterministic reports.
- [x] 5.2 Verify report/API/UI integration with Phases 0–4 and migrations from an existing DB.
- [x] 5.3 Run full backend/frontend suites, build, static checks and documented manual GIS checks; record actual results.
- [x] 5.4 Provide a user-supplied independent reference-data validation procedure and record status separately from software acceptance.
  - Procedure: `POST /projects/{id}/research/reference-areas` (area + source + method, uncertainty optional) →
    `GET /projects/{id}/research/area-error` → include the result in a report bundle. The first two steps only
    work with **operator-supplied** truth; the engine's own map is never accepted as a reference.
  - Status recorded separately: `GET /projects/{id}/research/status` keeps `software_validation` (this suite)
    apart from `scientific_validity`, which stays **"not established"** until such data exists — and does so today,
    because none does.
