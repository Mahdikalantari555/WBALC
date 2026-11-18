## Why

WBALC already has a working research-oriented foundation, but multiple roadmap layers are partial: water semantics are stored but not executed, query suggestions are not durably recorded, experiment lineage is incomplete, Scene records are not classified/analyzed temporally, and evaluation lacks temporal/generalization protocols. Implementing isolated features without cross-phase acceptance could still leave the application unable to support an end-to-end reproducible study.

## What Changes
- Define a dependency-ordered completion roadmap for Phases 0–5, linking the already drafted Phase 0 contract and five newly audited phase changes.
- Establish cross-phase integration requirements: immutable native sources, taxonomy/schema provenance, durable query-to-label-to-run lineage, scene/time-series linkage, no implicit grid alignment, reproducible evaluation and qualified reporting.
- Require a final synthetic end-to-end suite and an explicit software-complete versus externally scientifically validated status.

## Phase change set
- Phase 0: [`harden-pixel-classification-contract`](../harden-pixel-classification-contract/)
- Phase 1: [`phase-1-water-classification`](../phase-1-water-classification/)
- Phase 2: [`phase-2-active-learning-provenance`](../phase-2-active-learning-provenance/)
- Phase 3: [`phase-3-experiment-lineage`](../phase-3-experiment-lineage/)
- Phase 4: [`phase-4-temporal-water-mapping`](../phase-4-temporal-water-mapping/)
- Phase 5: [`phase-5-research-evaluation`](../phase-5-research-evaluation/)

## Impact
This roadmap change is the integration contract, not an implementation substitute. Each phase has its own proposal, design, requirements and task plan. Existing Phase 0 and multi-temporal foundation work is retained; no duplicate rewrite is intended.

## Non-goals
No one-shot rewrite, framework replacement, new dependency/job infrastructure without a phase design, real imagery download, or promise of scientific validity without independent field/reference data.
