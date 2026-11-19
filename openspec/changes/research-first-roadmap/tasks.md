## 1. Roadmap audit and specification
- [x] 1.1 Audit remaining roadmap phases against current APIs/models/services/tests/docs.
- [x] 1.2 Create separate Phase 1–5 audit/proposal/design/spec/tasks, retaining the existing Phase 0 OpenSpec.
- [x] 1.3 Define dependency order, global invariants and software-vs-scientific completion gates.

## 2. Ordered implementation gates
- [x] 2.1 Complete and verify Phase 0 (`harden-pixel-classification-contract`).
- [x] 2.2 Complete and verify Phase 1 (`phase-1-water-classification`).
- [x] 2.3 Complete and verify Phase 2 (`phase-2-active-learning-provenance`).
- [x] 2.4 Complete and verify Phase 3 (`phase-3-experiment-lineage`).
- [x] 2.5 Complete and verify Phase 4 (`phase-4-temporal-water-mapping`).
- [x] 2.6 Complete and verify Phase 5 (`phase-5-research-evaluation`).

## 3. Integrated acceptance
- [x] 3.1 Verify fresh install and upgrade migrations against current and legacy DB fixtures; preserve existing data/files.
- [x] 3.2 Add offline end-to-end synthetic workflow from immutable scene ingest through query/labels, train, inference, temporal analysis, held-out evaluation and report export.
- [x] 3.3 Verify no implicit source mutation/grid alignment, semantic schema confusion, label/test leakage or fabricated provenance.
- [x] 3.4 Run full backend/frontend tests, static checks and production build; record exact outputs and source revision.
- [ ] 3.5 Complete manual GIS overlay check and record evidence separately from automated tests.
- [x] 3.6 Report software completion and independent scientific-validation status separately; do not declare the latter without supplied reference data.
