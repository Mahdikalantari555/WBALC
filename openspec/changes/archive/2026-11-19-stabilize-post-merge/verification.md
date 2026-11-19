# RSAL post-merge stabilization — verification report

Change: `openspec/changes/stabilize-post-merge/` (audit: `audit.md`, scope:
`proposal.md`, decisions: `design.md`, tasks: `tasks.md`).
Branch: `arena/cad758ae-rsal`, based on `main` @ `d865c82`.
Date of verification: 2026-11-18.

## 1. Confirmed defects found

D1–D16 in `audit.md`. Summary by priority:

- **P0** — patch GeoTIFFs georeferenced on a stride lattice, so clamped edge cells
  were displaced (up to 2 px / 20 m on a 70×70 fixture) and exports overhung the
  source extent (D1); probabilities returned for cells the same response marked
  invalid (D2).
- **P1** — `/query` HTTP 500 after a pixel-resolution run (D3); invalid patches
  proposed by query/SOM (D4, D5); SOM pixel mode used any-band validity (D6);
  checkpoints loaded without validation, producing 500s and silent
  reinterpretation (D7).
- **P2** — resolution missing from predict/metrics responses (D8); stale export
  downloads (D9); no post-write verification for patch exports (D10); adapter
  dropped training options and `sample_resolution` (D11); no resolution label on
  the map (D12).
- **P3** — SOM `total_patches` counted nodata cells (D13); stale README/AUDIT
  claims (D14); incomplete license inventory (D15); open npm advisories (D16).

## 2. Defects fixed

| Defect | Fix | Regression test |
|---|---|---|
| D1 | Patch exports painted over true pixel windows on the source grid; `grid`/`resolution` tags; atomic writes | `TestPatchExportGeometry::test_patch_export_preserves_source_grid_on_clamped_edges`, `..._marks_stride_gaps_nodata` |
| D2 | `maps_from_inference` masks probabilities; `/predict` returns `null`; probability export always declares nodata | `TestInvalidMasks` (3 tests) |
| D3 | `/query` 409 for uncertainty/hybrid with a non-patch checkpoint; model-free strategies run with `notes` | `test_query_rejects_or_degrades_for_pixel_checkpoint` |
| D4 | Query candidates restricted to patches with valid pixels | `test_query_excludes_invalid_patches` (all four strategies) |
| D5, D13 | SOM explorer ignores non-patch checkpoints (`model_note`), fits/hits on valid patches only, reports `valid_patches`/`nodata_patches` | `test_som_explorer_ignores_pixel_checkpoint_and_invalid_patches` |
| D6 | SOM pixel validity is all-band | `test_som_pixel_mode_uses_all_band_validity` |
| D5 (export) | SOM GeoTIFF on the source grid, validated in both resolutions | `test_som_patch_export_matches_source_grid` |
| D7 | Validated checkpoints (`rsal-checkpoint-v2`: feature schema, feature count, class order); legacy v1 accepted only as patch; 409 with actionable messages | `TestCheckpoints` (4 tests) |
| D8 | `resolution` on predict/map/train/metrics; metrics expose strategy, `n_train`, `n_test`, `held_out_groups`, `per_class_iou` | `TestReportedContext` (2 tests) |
| D9 | Downloads re-infer when the newest export predates the latest run; `X-RSAL-Model-Iteration`/`X-RSAL-Export-Stale` | `TestDownloads::test_download_regenerates_stale_export` |
| D10 | Every export reopened and compared with the source window (both resolutions); artifacts deleted on failure; no export for datasets without CRS | D1 tests, `test_region_export_keeps_window_transform`, `test_export_refuses_ungeoreferenced_raster` |
| D11, D12 | Adapter forwards `resolution`/`evaluation_strategy`/`test_size`/`params` and `sample_resolution`; map states pixel vs patch cells; `MapField.resolution` end to end | `frontend/src/lib/server/payloads.test.ts` (4 tests) |
| D14 | README/AUDIT corrected (counts, export semantics, evaluation labels, limitations) | docs diff |
| D15 | License inventory rewritten with dependency paths and the full LGPL surface | docs diff |
| D16 | `postcss` 8.5.8 → 8.5.33 (only non-breaking fix available) | `npm audit` before/after |

## 3. Defects not fixed, and why

- **deck.gl/loaders.gl advisories (16 findings)** — only "fixed" by downgrading
  `deck.gl` to 9.1.0; the vulnerable loaders are not imported by the workspace.
  Needs an upstream release.
- **eslint-config-next → fast-glob/picomatch/micromatch advisories (11 findings,
  dev-only)** — `npm audit` proposes `eslint-config-next@14.2.35`, a major
  downgrade that would break the Next 16 build.
- **Rotated-grid previews** — exports are correctly georeferenced by affine copy;
  only the browser overlay/PNG preview is north-up. Documented, not a data error.
- **Streaming pixel inference** — needs an API/UX redesign; `MAX_RASTER_ELEMENTS`
  remains the guard.
- **Label identity by patch** — intentional versioning semantics; documented, and
  the adapter can now declare `sample_resolution: "pixel"`.
- **Forged `sample_id` in a label payload** — could supersede another sample's
  version history; geometry still decides training targets, so no training
  corruption was reproduced. Left as a documented limitation rather than
  changing the label identity contract inside a stabilization change.
- **OGC polygon topology validation** — unchanged, out of scope.

## 4. Files changed

Backend:
- `app/services/inference_service.py` — masked probabilities, atomic writers,
  cell-window exporters, `rasterize_cells`, `validate_export_grid`, tags.
- `app/services/training_service.py` — checkpoint format v2, feature schema,
  `validate_checkpoint`, validated `load_checkpoint`.
- `app/services/pipeline.py` — `checkpoint_or_409` validation/classes check.
- `app/api/inference.py` — resolution in responses, probability masking, export
  routing/validation, stale-download regeneration, CRS guard, headers.
- `app/api/query.py` — checkpoint compatibility, valid-candidate pool, notes.
- `app/api/som.py` — valid-only SOM, checkpoint compatibility, source-grid SOM
  export, strict pixel validity.
- `app/api/training.py`, `app/schemas.py` — resolution/evaluation fields, notes.

Frontend:
- `frontend/src/lib/server/payloads.ts` (new), `handler.ts`, `map-routes.ts`,
  `rsal.ts`, `payloads.test.ts` (new), `src/types/index.ts`,
  `src/components/map/map-viewer.tsx`, `package.json`/`package-lock.json`
  (`postcss` patch).

Tests:
- `tests/test_post_merge_stabilization.py` (new, 19 tests).
- Updated expectations to the corrected export contract and geometry assertions:
  `tests/test_inference_api.py`, `tests/test_map_layers_api.py`.

Docs/OpenSpec:
- `openspec/changes/stabilize-post-merge/{proposal,design,tasks,audit,verification}.md`
  and `specs/*/spec.md` (8 capabilities).
- `README.md`, `AUDIT.md`, `THIRD_PARTY_LICENSES.md`.

## 5. Tests actually executed

```bash
# backend (venv created from requirements-dev.txt)
.venv/bin/python -m pytest            # before: 139 passed
.venv/bin/python -m pytest            # after:  158 passed, 0 failed

# frontend
cd frontend
npm test                              # 25 tests, 25 pass
npm run typecheck                     # clean
npm run lint                          # 0 errors, 7 pre-existing warnings
npm run build                         # succeeded (Next 16 production build)

# dependencies
cd frontend && npm audit              # 29 (10 mod/19 high) -> 28 (10 mod/18 high)
.venv/bin/pip-audit -r requirements.lock.txt   # No known vulnerabilities found
.venv/bin/pip-audit -r requirements-dev.txt    # No known vulnerabilities found
```

Log of the executed pytest run: `158 passed, 1172 warnings in 54.33s`
(warnings are rasterio/Starlette/Pydantic deprecations, pre-existing).

## 6. Raster verification performed

- 70×70 scene, 8 px patches (clamped grid): export 70×70, affine/bounds equal to
  source, no overhang, every cell constant inside its recorded window.
- patch 4 / stride 8: uncovered strips nodata, covered strips classified.
- Region `{x0:8,y0:8,x1:40,y1:24}`: 32×16 export, affine translated by the
  window origin, cell windows recorded in absolute source pixels.
- 64×64 scene with a 16 px nodata collar (nodata=0): hard=65535, probability
  `null`/−9999, uncertainty `null`/−9999 and `valid=false` at every invalid cell;
  probabilities still sum to 1 where valid.
- Pixel-mode 64×64 run: same mask invariants per pixel; 1 px grid; exports on the
  window affine; the export's `grid` tag records `cells_are_pixels: true` rather
  than enumerating one cell per pixel (a multi-million entry tag otherwise).
- SOM pixel mode with one NaN band at one pixel: that pixel is nodata
  (`total_valid = 511`, `nodata_count = 513` on a 32×32 half-masked fixture).
- Ungeoreferenced dataset: `/predict` 422 with an explicit CRS error, map layer
  still served.

## 7. Dependency audit result

- Baseline: 29 advisories (10 moderate, 19 high); after: 28 (10 moderate, 18 high).
  Only `postcss` was resolvable without a major/downgrade change.
- Python runtime/dev requirement sets: no known vulnerabilities.

## 8. Remaining security / licensing concerns

- `deck.gl`'s transitive `@loaders.gl`/`@luma.gl`/`image-size` advisories remain
  (not imported by this app; need upstream).
- LGPL `@img/sharp*` binaries may be present in the Next.js server image; Esri and
  amCharts terms enter transitively through `deck.gl`; React-Leaflet is
  Hippocratic-2.1. Legal review is still required before redistribution.
- Checkpoints are joblib files: validated on load, but not a sandbox for
  third-party files placed on the server.

## 9. Known architectural limitations

Cell-map semantics of patch exports; synchronous single-process training and
inference with an element guard; 256 px spatial blocks; browser-local review
queue; API-only pixel training; SOM full-array loading with observation
subsampling; north-up browser previews of rotated rasters.

## 10. Is RSAL stable enough to serve as a WBALC reference?

**Qualified yes for correctness-critical behavior, with the listed limits.** All
confirmed P0/P1 defects in the audited scope are fixed and covered by
regression tests; pixel and patch modes are explicitly distinguished end to end;
exports are reopened and grid-verified; evaluation limitations are surfaced in
the API; checkpoint compatibility is enforced; both suites and the production
build pass. It is *not* declared fully stabilized: the dependency advisories that
require semver-major changes, the redistribution licensing review, streaming
inference and buffered spatial validation remain open and are documented — WBALC
should treat those as known constraints rather than solved problems.
