## Why

WBALC already proposes informative patches and stores label corrections, but the query list is mainly browser-local. A refresh or a different browser cannot reconstruct what was sampled, why it was selected, or how the annotator decided. Without a random baseline and durable batch records, strategies cannot be compared reproducibly.

## What Changes
- Add persistent query batch and item records containing Dataset, strategy/method, deterministic seed, candidate/model context, selected samples and scores/coordinates.
- Persist review decisions (labeled, rejected, deferred) and link submitted label versions to the corresponding query item where applicable.
- Add a seeded random patch-sampling baseline using the same valid/unlabeled candidate pool.
- Add API/UI history and resume behavior for batches; keep the browser queue as a cache, not the source of truth.
- Keep sampling resolution patch-based in this phase and clearly state limitations.

## Capabilities
### New: `query-batch-provenance`, `annotation-review-state`, `random-sampling-baseline`
### Modified: `active-learning-query`, `label-management`, `learning-workspace`.

## Impact
Additive persistence migration, query/label API schemas and services, batch history UI and synthetic API/database tests. No changes to source raster bytes.

## Non-goals
No authentication or shared-user roles, pixel-level query search, new uncertainty estimators, model training redesign, or full experiment tracking (Phase 3).
