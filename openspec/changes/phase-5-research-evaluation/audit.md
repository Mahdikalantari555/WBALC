# Phase 5 audit — Research evaluation

Audit date: 2026-11-18. Read-only review; no code/tests changed or run.

## Existing foundation
- Training supports stratified random holdout and block-grouped spatial holdout, with accuracy, macro/weighted F1, confusion matrix and per-class precision/recall/F1/IoU/support.
- Metrics retain evaluation strategy/sample counts; the frontend has iteration history/learning-curve and metrics views.
- Phase 3 proposes immutable run/data/artifact lineage; Phase 4 proposes scene-level temporal outputs.

## Gaps
- No temporal/scene-held-out evaluation protocol; current spatial blocks are fixed-size and unbuffered.
- No controlled benchmark suite comparing active-learning strategies, sensor sources, taxonomies, or pixel/patch products.
- No sensitivity/ablation protocol, uncertainty calibration/coverage evaluation, or area-estimation error evaluation.
- No consolidated report bundle exporting protocols, split membership, metrics, comparison tables, provenance and caveats.
- There is no real satellite reference dataset/field truth in the repository; synthetic tests can validate computation, not scientific accuracy.

## Phase boundary
Phase 5 provides reproducible protocol execution and transparent, article-ready machine-readable results. It does not assert the classifier is scientifically valid or accurate without independently supplied reference labels and an appropriate domain validation study.
