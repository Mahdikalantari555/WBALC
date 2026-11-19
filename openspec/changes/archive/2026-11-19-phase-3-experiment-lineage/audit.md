# Phase 3 audit — Experiment tracking and lineage

Audit date: 2026-11-18. Read-only review; no code/tests changed or run.

## Existing foundation
- `TrainingRun` stores project, iteration, model type, checkpoint path, class order, sample count, metrics, params and timestamp.
- Training params include resolution, evaluation strategy, random seed, test size, band count and Dataset IDs. Checkpoints include algorithmic feature family/count and class order.
- Metrics history and a frontend learning-curve/history view exist. Exports refer to Dataset and TrainingRun.

## Gaps
- No immutable Dataset content checksum/version or canonical band semantic identity is captured by run lineage.
- No label-set snapshot/hash, exact label version IDs, query-batch references, code/dependency version or checkpoint artifact checksum.
- No named Experiment/grouping entity for related runs, protocol comparison, or a complete lineage manifest.
- Legacy records cannot be retroactively assigned unknown provenance; must be marked incomplete.

## Phase boundary
Phase 3 makes data/configuration/model/output lineage reproducible and supports named, comparable experiments. Durable query batch implementation is Phase 2; Phase 3 links to it. Research protocol suites/reports belong to Phase 5.
