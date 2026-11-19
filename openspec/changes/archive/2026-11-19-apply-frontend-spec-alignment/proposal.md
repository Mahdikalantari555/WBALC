# Apply the remaining research specs to the frontend

## Why

`wire-geospatial-research-frontend` turned the SvelteKit example into a live,
bilingual research workspace. Five further changes in `openspec/changes/`
(`harden-pixel-classification-contract`, `phase-1-water-classification`,
`phase-2-active-learning-provenance`, `phase-3-experiment-lineage`,
`phase-5-research-evaluation`) are written against the engine, but each of them
also constrains what a *workspace* may claim. Those frontend-facing clauses are
currently unimplemented: the app has no way to train a model at all, it shows a
binary interpretation as if the engine emitted one, it presents random-holdout
scores without a caveat, and it compares runs without saying what differs.

## What changes

Frontend-only adoption of the interface-facing requirements of those specs.
No backend, RSAL schema, endpoint or migration changes.

1. **Explicit training control** (harden 4.1 / 5.5). New adapter route
   `POST /api/projects/{id}/train` and a learning-workspace panel where the
   operator picks resolution (`patch` | `pixel`), validation split
   (`random` | `spatial`) and model family. The route validates both enums,
   never relies on the engine default, and returns the run so its provenance is
   visible immediately.
2. **Resolution is never implicit** (harden 4.1, pixel-classification spec).
   The chosen resolution is echoed on the run, in the ranking table, in the
   metrics table caption and in evaluation exports; the map states whether a
   field is "one value per source pixel" or "one value per Npx patch cell".
3. **In-sample scores are labelled** (phase-5 research-evaluation). When the
   engine reports `insufficient_train*`, the overview, arena, metrics table,
   evaluation protocol panel and JSON/CSV exports all say the numbers are
   in-sample instead of presenting them as validation.
4. **Random-holdout caveat** (phase-5). Where the recorded protocol is `random`,
   the UI says a random holdout over neighbouring patches is optimistic and
   points at spatial holdout for reporting.
5. **Run comparison states its differences** (phase-3 experiment-lineage). The
   arena lists the recorded fields that differ between run A and run B
   (resolution, protocol, sample count, model family, taxonomy, scoring) so two
   scores are not shown as like-for-like when they are not.
6. **Binary interpretation is marked as not yet produced** (phase-1
   water-classification). The project config is displayed with the explicit note
   that this engine version does not emit a separate binary product, rather than
   implying a product exists.
7. **Study-area masking is marked as not yet applied** (harden 3.x,
   phase-4). The map states that predictions are masked by source-raster
   validity only, even when a study area is configured.
8. **Label distribution counts samples, not rows** (phase-2). Corrections no
   longer inflate a class in the evaluation view.
9. **Georeferencing reasons are localized, not English codes.** Adapter reason
   codes are mapped to translated explanations instead of being shown verbatim.

## Impact

- Frontend only: `examples/wbalc-geospatial-research-interface/`.
- New route, one client method, one state action, one learning panel, honesty
  blocks on overview / map / arena / evaluation, ~25 new i18n keys in both
  dictionaries.
- Existing tests extended (adapter, jsdom components) and the live smoke
  extended to train through the adapter and reject bad enums (63 checks).

## Non-goals

- No backend implementation of pixel mode, study-area masking, band-schema
  identity, experiment groups, artifact checksums or binary exports. Those need
  engine work and remain owned by their own changes.
- No mock or placeholder values for the above: the UI states the limitation.
- No changes to `frontend/` (the Next.js TerraLab workspace) or to `app/`.
