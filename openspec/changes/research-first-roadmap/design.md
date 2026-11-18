## Scope audit and current baseline

Read-only audit performed 2026-11-18 on the active WBALC branch. Existing foundations include multi-temporal Scene metadata and grid comparison; synthetic native-grid/pixel inference tests; RF/LightGBM and SOM; multiple patch-query strategies; label version history; checkpoint v2 feature-family/count validation; random/spatial holdout and standard classification metrics. Existing gaps and phase requirements are documented in each phase `audit.md`.

Important correction: checkpoint v2 already identifies `pixel-band-vector` versus `patch-band-stats` and feature count; the remaining semantic gap is ordered band identity/sensor schema in Dataset/model lineage, not absence of all feature-schema validation. Existing README reports 171 backend tests and 25 frontend tests historically; this planning audit did not rerun them.

## Dependency order

1. **Phase 0 — pixel/geospatial correctness contract.** Finish explicit reference identity, project study-area mask, semantic band schema, honest resource limit, user-visible pixel training and synthetic/manual verification. This is prerequisite to trustworthy scene products.
2. **Phase 1 — water taxonomy/products.** Establish canonical classes, label crosswalk and binary output semantics before collecting durable strategy-linked annotation and temporal area products.
3. **Phase 2 — durable annotation/AL.** Persist query batches, random baseline and decisions. It may start after Phase 1 so all saved labels use stable taxonomy.
4. **Phase 3 — experiment lineage.** Link exact Dataset content, label snapshots, batches, runs, checkpoints and outputs; depends on Phase 2's durable batch identity.
5. **Phase 4 — temporal mapping.** Classify registered Scenes, calculate area/change and controlled late fusion with Phase 1 taxonomy and Phase 3 manifests.
6. **Phase 5 — research evaluation.** Temporal/spatial protocols, controlled strategy/fusion comparisons and report bundles build on immutable lineage and Phase 4 products.
7. **Integration acceptance.** Run migrations from existing schemas, end-to-end synthetic workflows, full backend/frontend checks, manual GIS review and qualification of external scientific validation.

Phase dependencies are a recommended sequence; teams may implement independent UI/API foundations in parallel only when contracts are kept stable and integration gates are preserved.

## Completion definition

The software roadmap is complete only when every phase's requirements/tasks are implemented and verified, and the integrated workflow can: register untouched scenes; define taxonomy/study region; create labels and durable query batches; train a schema-compatible model; produce masked native-grid scene classifications; compute qualified per-date area/change outputs; compare/fuse only under explicit operations; trace every output to immutable inputs/configs/runs; execute leak-free held-out protocols; and regenerate a qualified report bundle.

Software completion is distinct from scientific validity. The repository has no field/reference imagery or labels; that external validation status remains `not established` until a user supplies suitable independent data and records the evaluation.

## Cross-cutting invariants

- Original uploaded imagery remains byte-immutable; all schema evolution is explicit, additive and migration-tested.
- Native grids, sensor-specific bands and class semantics remain distinct. No default 10/20 m scale, hidden reprojection, resampling or grid-equivalence claim.
- Categorical alignment, if requested in Phase 4, is an explicit derived operation on a user-selected grid with nearest-neighbor and provenance.
- Every metric is attached to its split, sample/scene support and exact lineage; unsupported values are null/insufficient, never fabricated.
- Tests use deterministic synthetic GeoTIFFs and never require real satellite data or internet.
- Existing generic projects, patch workflows and historical rows remain supported or are explicitly marked incompatible; no silent semantic migration.

## Risks

The total scope is substantial and can become a monolith. Keep each numbered phase a separate OpenSpec change and code review. Do not mark tasks complete until tests/evidence exist. Data model additions need migration tests against current and pre-existing schemas. Research reports can be reproducible without being scientifically valid.
