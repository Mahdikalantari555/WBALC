## 1. Audit
- [x] 1.1 Reproduce baseline (139 backend tests green; npm audit 29 findings; pip-audit clean for runtime)
- [x] 1.2 Reproduce export misalignment, probability leak, query/SOM 500s, invalid-patch candidates, checkpoint failure, stale download, frontend adapter gaps
- [x] 1.3 Write `audit.md` with confirmed defects (D1–D16), hypotheses and deferred items

## 2. Raster and export correctness
- [x] 2.1 Cell-window writers for hard/probability/uncertainty that paint cells onto the source grid, stream row blocks, write `.tmp` + atomic rename and set `grid`/`resolution`/`nodata` tags
- [x] 2.2 Validate every written export by reopening it and comparing dims/CRS/affine/bounds with the source window (both resolutions), deleting artifacts on failure
- [x] 2.3 Mask probabilities in `maps_from_inference`; `/predict` returns `null` for invalid cells
- [x] 2.4 Keep pixel exports one-value-per-pixel and byte-for-byte aligned with the window transform
- [x] 2.5 Tests: clamped-edge patch export geometry, odd dimensions, non-square pixels, region windows, reopen verification, probability/uncertainty invalid masking

## 3. Checkpoints
- [x] 3.1 `save_checkpoint` records `feature_schema`/`n_features` (format v2) and patch/pixel resolution
- [x] 3.2 `load_checkpoint` validates format/keys/classes/bands/resolution and raises `TrainingError`; legacy v1 accepted only as patch
- [x] 3.3 `checkpoint_or_409` maps validation failures to actionable 409s; expose `legacy` flag
- [x] 3.4 Tests: missing key, wrong format, class-order drift, pixel-vs-patch feature mismatch, legacy v1

## 4. Active learning query integrity
- [x] 4.1 Reject `/query` with a non-patch checkpoint for uncertainty/hybrid (409); run model-free strategies with `model_iteration: null` + `notes`
- [x] 4.2 Exclude patches without valid pixels from the candidate pool
- [x] 4.3 Tests: pixel checkpoint (all four strategies), nodata collar (uncertainty + diversity), labeled exclusion unaffected

## 5. SOM
- [x] 5.1 Explorer uses a checkpoint only when it is a patch checkpoint with matching bands; otherwise notes why
- [x] 5.2 Explorer excludes invalid patches from fit/hits/cells and reports `valid_patches`/`nodata_patches`
- [x] 5.3 Pixel-mode classification uses strict all-band validity
- [x] 5.4 SOM GeoTIFF written on the source grid and validated for both resolutions
- [x] 5.5 Tests: explorer counts, pixel validity, export grid

## 6. API contract
- [x] 6.1 `predict`, `predict/map`, `train`, `metrics` report `resolution`
- [x] 6.2 Metrics report `evaluation_strategy`, `n_train`, `n_test`, `held_out_groups`, `per_class_iou`, `evaluation_warning`
- [x] 6.3 `GET /download/{type}` regenerates stale exports and sets iteration/stale headers
- [x] 6.4 Tests for all of the above

## 7. Frontend
- [x] 7.1 Adapter forwards `resolution`, `evaluation_strategy`, `test_size`, `params` to `/train`; types updated
- [x] 7.2 Adapter sends `sample_resolution` for pixel-mode point labels
- [x] 7.3 Map states the field resolution (pixel vs patch) next to the cell size
- [x] 7.4 `MapField` type + BFF mapping carry `resolution`
- [x] 7.5 `npm run typecheck && npm run lint && npm test && npm run build`

## 8. Dependencies and licensing
- [x] 8.1 Re-run `npm audit`; apply non-major fixes (postcss, typescript-eslint chain) and re-run tests/build
- [x] 8.2 `pip-audit` the runtime environment; record result
- [x] 8.3 Correct `THIRD_PARTY_LICENSES.md` (dependency paths, LGPL surface, package counts, audit counts)

## 9. Documentation
- [x] 9.1 Correct README test counts, query strategy count, evaluation labels, export semantics, resolution modes, NoData rules, AL persistence, limitations
- [x] 9.2 Update `AUDIT.md` with this change's confirmed/fixed/open defects and executed verification
- [x] 9.3 Final verification report with executed commands and results

## 10. Verification
- [x] 10.1 Full backend suite green (count recorded)
- [x] 10.2 Frontend typecheck/lint/test/build green (counts recorded)
- [x] 10.3 Raster outputs verified by reopening synthetic fixtures (pixel and patch, odd dims, nodata, region)
