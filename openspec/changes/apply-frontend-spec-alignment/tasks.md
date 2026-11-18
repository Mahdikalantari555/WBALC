# Tasks — apply the remaining research specs to the frontend

Scope: `examples/wbalc-geospatial-research-interface/` only. Checkboxes are
ticked only where code and verification both exist.

## 1. Explicit training (harden-pixel-classification-contract 4.1, 5.5)

- [x] 1.1 Add `POST /api/projects/{id}/train` adapter route returning a `RunView`; verify against live RSAL.
- [x] 1.2 Reject unknown `resolution` / `evaluationStrategy` values with 400 before calling the engine; verify both rejections.
- [x] 1.3 Add `workspace.train()` + `api.train()`; verify the new run appears first in the runs list and becomes arena A.
- [x] 1.4 Add the learning-workspace training panel (resolution, split, model) with a consequence sentence per choice; verify typecheck + build.
- [x] 1.5 Echo the recorded resolution and protocol wherever a score is displayed (arena table, config panel, metrics caption, evaluation panel, CSV/JSON).

## 2. Honest score semantics (phase-5-research-evaluation, phase-3-experiment-lineage)

- [x] 2.1 Label in-sample fits on overview, arena, metrics table and evaluation protocol panel.
- [x] 2.2 Add the random-holdout caveat separately from the insufficient warning.
- [x] 2.3 Add `protocolCaveat` + `insufficient` column to the JSON/CSV evaluation exports.
- [x] 2.4 List the recorded fields that differ between arena run A and run B; verify the note only appears when they differ.
- [x] 2.5 Unit-test `toRun` provenance mapping and the insufficient passthrough.

## 3. Taxonomy, product and mask honesty (phase-1, phase-4, harden 3.4)

- [x] 3.1 Show the binary interpretation with an explicit "not emitted by this engine version" note.
- [x] 3.2 Show the study area with an explicit "predictions are not clipped to it yet" note, only when a geometry is configured.
- [x] 3.3 Translate georeferencing reason codes instead of printing adapter identifiers.
- [x] 3.4 Keep patch/pixel wording distinct on the map and in the learning panel.

## 4. Active-learning provenance wording (phase-2)

- [x] 4.1 Count the evaluation label distribution per distinct sample, not per label row; verify corrections do not inflate a class.
- [x] 4.2 Keep the browser-scoped queue wording (no user, permission or collaboration claim).

## 5. Verification

- [x] 5.1 `npm run check` → 0 errors, 0 warnings.
- [x] 5.2 `npm test` → 40 tests in 4 files pass (includes jsdom component tests).
- [x] 5.3 `npm run check:i18n` → 325 keys complete in `en.ts` and `fa.ts`.
- [x] 5.4 `npm run build` (adapter-node) succeeds.
- [x] 5.5 `scripts/research_frontend_smoke.py` → 63 checks pass on dev **and** on the production build.
- [x] 5.6 Confirm no backend/frontend-Next.js file changed by this work.

## 6. Out of scope (engine work, tracked by their own changes)

- [ ] 6.1 Band/schema identity and mismatch overrides (harden 2.x).
- [ ] 6.2 Study-area masking in inference and exports (harden 3.1–3.3).
- [ ] 6.3 Out-of-core / limited-memory inference (harden 4.2).
- [ ] 6.4 Binary interpretation products and crosswalk persistence (phase-1).
- [ ] 6.5 Durable batches, decisions and seeds (phase-2).
- [ ] 6.6 Manifests, checksums, experiment groups (phase-3).
- [ ] 6.7 Calibration, coverage and area error (phase-5).
- [ ] 6.8 Scene classification and area-change products (phase-4).
