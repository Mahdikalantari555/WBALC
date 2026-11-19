## Why

Current metrics provide a useful first evaluation but cannot establish temporal generalization or support controlled claims about Active Learning, sensor choice, water-area estimates or uncertainty. The final roadmap phase adds protocol-driven evaluation and a transparent report bundle, building on Phase 3 lineage and Phase 4 temporal products.

## What Changes
- Add reproducible random, spatially buffered/grouped and acquisition-time/scene-held-out evaluation protocols with persisted sample/split membership and no train/test overlap.
- Add controlled comparison/ablation runs for pixel versus patch, AL strategy including random baseline, supported sensor-specific models/fusion, class taxonomy and model parameters.
- Report per-class confusion/precision/recall/F1/IoU, balanced accuracy, uncertainty calibration/coverage where applicable, and water-area error only when a reference-area source is supplied.
- Add sensitivity analysis with declared parameter ranges/seeds and uncertainty summaries across repetitions; do not treat repeated seeds as independent scenes.
- Export a reproducible research bundle (JSON/CSV plus a human-readable Markdown/HTML summary) containing manifests, protocols, splits, metrics, hashes and limitations.
- Add synthetic verification of calculations and an optional user-supplied evaluation-dataset workflow; no bundled real imagery or accuracy thresholds.

## Capabilities
### New: `research-evaluation-protocols`, `benchmark-comparison`, `research-reporting`
### Modified: `experiment-management`, `temporal-change-analysis`, `analytics`.

## Impact
Training/evaluation service, experiment/run schema, split management, metrics/report API and frontend comparison/export views. Depends on Phases 1–4 and their recorded semantics. Additive migrations only.

## Non-goals
No fabricated benchmark/ground truth, automatic internet data access, publication claims, arbitrary universal acceptance accuracy threshold, or guarantee that a reproducible experiment is externally valid.
