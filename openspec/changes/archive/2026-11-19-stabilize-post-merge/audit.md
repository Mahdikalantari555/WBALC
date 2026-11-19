# Audit — post-merge stabilization (2026-11-18)

Audit performed on `main` at `d865c82` (merge of the pixel/geospatial stabilization
PR) before any file was modified. Every entry below was reproduced against the
current code with synthetic fixtures; hypotheses are listed separately.

Reproduction artefacts are in `tests/` after the fix (each confirmed defect has a
regression test named in the table). The baseline suite was green before the
change: **139 passed** (`pytest`, Python 3.11, venv). Baseline `npm audit`:
**29 advisories — 10 moderate, 19 high**; `pip-audit` on the runtime environment:
0 runtime findings (only `pip`/`setuptools` in the dev venv).

## Confirmed defects

| # | Prio | Area | Defect | Evidence |
|---|---|---|---|---|
| D1 | P0 | Raster export | Patch-mode GeoTIFFs are written on a uniform stride lattice that cannot represent the edge-clamped grid. On a 70×70 scene with 8 px patches, 17 of 81 cells are displaced by up to 2 px (20 m) and the export extends 20 m past the source extent (`bounds` right 500720 vs 500700). The `grid` tag documents the true windows, so the raster contradicts its own metadata. | `test_patch_export_preserves_source_grid_on_clamped_edges` |
| D2 | P0 | Inference masks | `probability_map` in `POST /predict` is not masked for invalid cells: all-nodata pixels/cells return probabilities summing to 1.0 while `valid_map=false` and `hard_map=65535`. Probability and uncertainty therefore carry different masks. | `test_predict_probability_map_masks_invalid_cells` |
| D3 | P1 | Active learning | `POST /query` uses the patch feature schema unconditionally. After a pixel-resolution run, every strategy returns HTTP 500 (`predict_proba` feature-count mismatch). | `test_query_rejects_or_degrades_for_pixel_checkpoint` |
| D4 | P1 | Active learning | Query candidates include patches with no valid pixels. On a scene with a nodata collar, the top-10 uncertainty batch was 10/10 invalid patches (confidence 0.8, uncertainty 0.2), and a 64-sample diversity batch returned all 16 invalid patches. | `test_query_excludes_invalid_patches` |
| D5 | P1 | SOM explorer | `GET/POST /som` has the same checkpoint problem (HTTP 500 with a pixel-resolution run) and fits the map on invalid patches: a scene with 25 % nodata reports `total_patches=64` and `hit_grid` sums to 64, so nodata cells are clustered and offered as samples. | `test_som_explorer_ignores_pixel_checkpoint_and_invalid_patches` |
| D6 | P1 | SOM classify | Pixel-mode SOM uses `np.isfinite(...).any(axis=1)`, i.e. a pixel with one nodata band is classified (and its NaN bands imputed), unlike supervised pixel mode which requires all bands. `total_valid` counted 2048 of 4096 pixels including a partially masked pixel. | `test_som_pixel_mode_uses_all_band_validity` |
| D7 | P1 | Checkpoints | `load_checkpoint` is a bare `joblib.load` with no validation. A checkpoint missing `bands` produces HTTP 500 (`KeyError`) on `/predict`; unknown/older payloads are silently reinterpreted as patch mode; nothing rejects a feature-schema/resolution mismatch. | `test_checkpoint_validation_rejects_incompatible_payloads` |
| D8 | P2 | API contract | `POST /predict` and `GET /predict/map` never report the classification resolution, so a client cannot tell a 1-class-per-pixel map from a patch-cell map. `TrainResponse`/`MetricsOut` also omit `resolution`, `evaluation_strategy`, `n_train`, `n_test` and `held_out_groups` even though they are persisted in `run.params`/`metrics`. | `test_predict_and_metrics_report_resolution` |
| D9 | P2 | Exports | `GET /download/{type}` serves the newest export of a type even when it predates the latest training run (reproduced: after retraining at patch resolution, `download/hard` still returned the 64×64 pixel-mode export). No iteration/stale signal is attached to the response. | `test_download_regenerates_stale_export` |
| D10 | P2 | Exports | Export files are written straight to their final path with no re-open validation for patch mode, so a partially written or geometrically wrong artifact can be served (pixel mode is validated). | covered by D1 test + `test_exports_are_reopened_and_match_source_grid` |
| D11 | P2 | Frontend adapter | `POST /train` through the adapter forwards only `model_type`: `resolution`, `evaluation_strategy`, `test_size` and `params` cannot be selected, and the response type drops them. `RsalLabel`/`toRsalLabel` never sends `sample_resolution`, so pixel-mode point labels collected through the UI collapse to patch identity (silent label merge). | `frontend/src/lib/server/handler.test.ts` |
| D12 | P2 | Frontend UI | The map reports `1 cell = N px` but not whether the field is a pixel or patch classification; the layer wins are keyed by dataset/layer/method and a stale field after a failed request keeps the previous image with no stale marker in the failure path. | `map-field` type + component change; covered by typecheck/build |
| D13 | P3 | SOM/usage | `total_patches` in the SOM explorer counts invalid patches, so the UI's patch count and "labeled" coverage are inflated on scenes with nodata collars (see D5). | `test_som_explorer_ignores_pixel_checkpoint_and_invalid_patches` |
| D14 | P3 | Docs | `README.md` claims "82 tests" (139), "all three query strategies" (four), `evaluation: "train"` (code returns `insufficient_train_metrics`), and describes patch exports as a padded lattice, which is not what is written. `AUDIT.md` repeats the padded-lattice claim. | docs diff |
| D15 | P3 | Licensing | `THIRD_PARTY_LICENSES.md` lists packages without dependency paths and understates the LGPL surface (14 `@img/sharp*` entries, all LGPL-3.0-or-later); it does not state that ArcGIS/amCharts enter only through `deck.gl → @deck.gl/arcgis → @arcgis/core → @amcharts/amcharts5`. | docs diff |
| D16 | P3 | Security | The historical npm counts reproduce (29/10/19). `postcss` (direct, dev) and the `typescript-eslint` chain are fixable without major upgrades; the rest (deck.gl 9.4.1 meta-package → loaders.gl/luma.gl, `eslint-config-next` 16.4.5 → fast-glob/picomatch/micromatch) only resolve through major/downgrade changes. | `npm audit` before/after |

## Potential defects requiring reproduction (not fixed)

- **P2 — Rotated/skewed rasters in exports.** Pixel exports copy the source affine
  verbatim, so a rotated source produces a rotated output that `validate_grid_compatibility`
  accepts; patch exports are now painted on the source grid, so they inherit the same
  rotation. No endpoint resamples, so no rotated-grid interpolation bug was found, but
  the frontend warped overlay and the PNG/CSV previews are north-up pictures of a
  possibly rotated grid. Not reproducible as data loss with the current endpoints;
  documented as a limitation instead.
- **P2 — `stride > patch_size` leaves unclassified gaps.** The grid intentionally
  allows gaps; patch exports mark gaps nodata. Not a defect, but no endpoint warns the
  user that the extent is partially unclassified. Documented.
- **P3 — Duplicate labels in the same patch.** Points submitted without
  `sample_resolution: "pixel"` share a patch identity, so a second point in the same
  patch replaces the first (documented behaviour; reproduced: 6 labels → 4 samples).
  Fixed only in documentation and the frontend adapter (D11), not by changing label
  identity, because the versioning model depends on `sample_id`.
- **P3 — `GET /history` / label deletion** uses sample ids only; a label for another
  dataset with a forged `sample_id` can supersede a real sample. Geometry still decides
  training targets, so no training corruption was reproduced.
- **P3 — Large-raster memory.** Pixel inference keeps full probability cubes and the
  `MAX_RASTER_ELEMENTS` guard is the only protection. Streaming inference is out of scope.

## Missing tests found during the audit

- No test asserted the patch export's real cell geometry on non-divisible dimensions.
- No test asserted that invalid cells have masked probabilities (only the hard map).
- No test covered query/SOM behaviour with a pixel-resolution checkpoint or with
  invalid patches in the candidate pool.
- No test exercised checkpoint validation (missing keys, wrong format, resolution
  mismatch).
- No test asserted `resolution`/`evaluation_strategy` in API responses.
- No test asserted stale-export regeneration.

## Deliberately deferred

- Streaming pixel inference / probability output (needs an API redesign).
- Full OGC polygon topology validation (unchanged from the previous change).
- Major upgrades of `deck.gl`/`eslint-config-next` (semver-major or downgrade;
  `npm audit fix --force` would break the workspace).
- Legal review of LGPL binaries and the Esri/amCharts/Hippocratic terms.
- Domain-specific spatial block size (still 256 px).
- A UI control for pixel-resolution training (API-only for now; documented).
