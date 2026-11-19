# Design — frontend adoption of the remaining research specs

## Decision: which requirements belong to the frontend

Each remaining change mixes engine work with interface obligations. The split
used here is: **the frontend implements every clause that is about what is shown,
enabled or submitted, and states the limitation for every clause that needs
engine work.** Nothing is simulated. The mapping:

| Change | Frontend obligation | Engine work left out |
| --- | --- | --- |
| harden-pixel-classification-contract | 4.1 (explicit resolution in UI requests), 5.5 (contract/provenance display), 3.4 (patch vs pixel wording), honest processing-limit labels | 2.x band-schema identity, 3.1–3.3 study-area mask, 4.2 streaming limits |
| phase-1-water-classification | taxonomy and binary interpretation displayed with stable IDs and a "not applied yet" note | crosswalk persistence, binary recoding, config snapshots |
| phase-2-active-learning-provenance | no collaboration claim; decisions/resume stay browser-scoped; label distribution counts samples | durable batch records, decision states, seeds, pool hashes |
| phase-3-experiment-lineage | show recorded differences between compared runs; never claim identical inputs | manifests, checksums, experiment groups, artifact verification |
| phase-5-research-evaluation | label in-sample scores; report held-out counts, protocol, resolution; qualify exports | calibration/coverage, area-error, report bundles |
| phase-4-temporal-water-mapping | continue to refuse area-change series without validated semantics | scene classification, area products, alignment operations |

## Training control

`POST /api/projects/{id}/train` exists because the UI must be able to train
without knowing the engine URL, and because the two enums are the whole point of
the harden change: `resolution` and `evaluation_strategy` both default in the
engine, and both change what the resulting number means. The adapter therefore:

- rejects anything outside `patch|pixel` and `random|spatial` with 400 before
  calling the engine, so a typo cannot silently become a default;
- sends both values explicitly even when they match the engine default;
- returns the `TrainResponse` shaped by `toRun`, so the same provenance fields
  the engine recorded appear in the runs list immediately.

The learning view exposes the pair as named selects with a one-line consequence
sentence each ("one prediction per patch cell; not independent pixels", "a random
holdout over neighbouring patches is optimistic"). The engine's `409`/`422`
detail is still surfaced verbatim when, for example, there are too few labels.

## Honesty surfaces

All of these read the *recorded* provenance rather than guessing, and none of
them hides a number; they add context:

- **`insufficient`** is derived once, in `toMetrics`, from
  `evaluation.startsWith('insufficient_train')`. Every surface consumes that flag
  (overview note, arena note, metrics-table badge, evaluation protocol panel,
  JSON `protocolCaveat`, CSV `insufficient` column).
- **Random holdout** is a separate, weaker statement than "insufficient": the
  score is real, but optimistic. It gets its own note rather than being folded
  into the insufficient warning.
- **Arena differences** are computed from `MetricsView` fields the engine already
  records. Because the engine does not yet expose content manifests, the UI says
  exactly which fields differ and never asserts the inputs were equal.
- **Study area / binary product** notes are driven by project config presence,
  not by a constant, so they disappear automatically once the engine implements
  the behaviour.

## Localization of reason codes

`georefReason` values are adapter-level identifiers (`unsupported-crs`, …). The
map maps them to dictionary keys before display; an English code leaking into the
Persian UI was a real inconsistency, and the fix is a mapping, not a `String()`
fallback.

## Testing

- Unit: adapter run mapping (resolution + protocol echoed, insufficient
  preserved), i18n completeness (both dictionaries, placeholder parity).
- Component (jsdom): locale switch flips chrome *and* `dir` with no reload;
  `MetricsTable` shows model/protocol/resolution and badges an in-sample fit.
- Live smoke (63 checks): trains through the adapter, asserts the echoes, and
  asserts bad enums are rejected with 400 before any work happens.

## Compatibility

`npm run check`, `npm test`, `npm run check:i18n`, `npm run build` and the smoke
all pass on the dev server and on the adapter-node production build. No backend
file is touched; `frontend/` (Next.js) is untouched.
