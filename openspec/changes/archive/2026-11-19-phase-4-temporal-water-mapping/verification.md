# Phase 4 verification — temporal water mapping, areas and late fusion

Change: `phase-4-temporal-water-mapping`
Branch: `arena/a4a6bd6b-wbalc`
Verification date: 2026-11-19 (sandbox clock) — synthetic data only.

## What shipped

### Backend

| Area | Implementation |
| --- | --- |
| Immutable scene analysis record | `SceneAnalysis` model (`app/models.py`), migration **v008** (`app/migrations/v008_scene_analysis.py`, additive: two new tables, `checkfirst=True`) |
| Native-grid classification | `POST /projects/{id}/scenes/{scene_id}/classify` (`app/api/temporal.py` → `app/services/scene_service.py`) |
| Explicit schema contract | `require_compatible_model` compares the model's declared band schema with the *scene's own* declared band names/descriptions (or polarization only when the count matches). Equal band counts never suffice; `accept_unverified_schema` is an explicit, recorded override. |
| Study area | Reuses `mask_service.study_area_mask` (pixel-centre inclusion) on the whole scene; the rule and note are stored in `study_area` on the analysis and in the GeoTIFF tags. |
| Products | hard / probability / uncertainty GeoTIFFs written atomically on the scene's exact affine, each with a recorded SHA-256 + size. |
| Area math | `app/services/area_service.py`: projected `|det(affine)| × unit²→m²`; geographic exact WGS84 ellipsoid integration per pixel row (the WGS84 assumption is recorded, not implied). Unknown linear units → areas reported **unavailable** with a reason. |
| Per-date areas | `GET /projects/{id}/temporal/series` — per-class/binary water areas, valid coverage, pixel-area method per date, plus caveats for mixed taxonomies and differing grids. |
| Change analysis | `POST /projects/{id}/temporal/compare` — transition matrix over the **jointly valid** footprint, changed/unchanged areas, denominators, caveats. |
| Grid mismatch | Fails closed with a structured `409 {error: "grid_mismatch", differences[], resampling_options["nearest"], hint}`. |
| Explicit alignment | Only via `reference_scene_id` (must be one of the two scenes), nearest-neighbour, recorded in `alignment` + `lineage.comparison_digest`; native products untouched. |
| Late fusion | `POST /projects/{id}/fusion` with `rule ∈ {weighted_probability, weighted_vote, priority}`, declared target scene grid, per-sensor weights, `missing_policy ∈ {require_all, renormalise}`; per-source analyses/digests preserved; agreement statistics; fused hard map checksummed. `early_fusion` / `raw_band_fusion` → `422 early_fusion_rejected`. |
| Export integrity | `GET /projects/{id}/analyses/{analysis_id}/exports/{kind}` re-verifies the checksum **and** reopens the GeoTIFF to prove it is still on the recorded grid, and checks the scene source bytes still match the recorded content hash. Tampering → `409`, record untouched. |

### Frontend

- `Temporal.svelte`: per-date result cards (native-grid badge, area method, class/water areas, verified downloads), a per-date series table with caveats, an explicit change panel (compare → on mismatch, choose which grid to align onto), and a fusion panel (rule, target grid, missing policy, per-source weights + aligned badges, agreement, digest).
- `Evaluation.svelte`: "Single-sensor vs fused products" panel listing every recorded fusion next to the per-date single-sensor areas, with rule, sources, weights, water area, agreement and digest.
- Adapter/route layer: `toSceneAnalysis`, `toAreaSummary`, `toTemporalSeries`, `toTemporalComparison`, `toFusion`; routes under `/api/projects/{id}/scenes/{sceneId}/classify`, `.../analyses`, `.../temporal/series`, `.../temporal/compare`, `.../fusion`, `.../analyses/{analysisId}/exports/{kind}`.
- i18n: 487 keys in `en.ts` and `fa.ts` (was 412).

## Commands actually run

```
.venv/bin/python -m pytest -p no:warnings                    # 301 passed in 91.80s
.venv/bin/python -m pytest tests/test_temporal_phase4.py -q   # 32 passed
cd examples/wbalc-geospatial-research-interface
npx svelte-check --tsconfig ./tsconfig.json                  # 0 errors, 0 warnings
npx vitest run                                               # 5 files, 69 tests passed
node scripts/check-i18n.mjs                                  # 487 keys in en.ts and fa.ts
npx vite build                                               # adapter-node, done
.venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
                                                             # 118 checks passed
```

`tests/test_scenes_api.py` migration assertion updated to expect version 8.

## Coverage of the spec's acceptance themes

- **Projected vs geographic area** — `test_projected_pixel_area_is_det_times_unit_squared`,
  `test_projected_pixel_area_honours_non_metre_units` (US survey feet),
  `test_projected_pixel_area_refuses_unknown_linear_unit`,
  `test_geographic_pixel_area_matches_known_ellipsoid_values` (1°×1° at the equator =
  12,308.46 km², and 6,123.14 km² at 61°N),
  `test_geographic_area_varies_by_row_and_is_reported`, `test_missing_crs_reports_unsupported_rather_than_guessing`.
- **Valid denominator / nodata** — `test_area_by_class_excludes_invalid_pixels_and_reports_coverage`,
  `test_area_by_class_honours_explicit_nodata_sentinel`, `test_water_area_only_counts_declared_water_classes`.
- **Change excludes nodata** — `test_transitions_use_the_jointly_valid_footprint`,
  `test_transitions_reject_mismatched_shapes_instead_of_broadcasting`.
- **Schema mismatch** — `test_classification_is_refused_without_a_provable_band_schema`,
  `test_classification_refuses_a_different_sensor_schema`.
- **Grid mismatch / explicit alignment** — `test_compare_refuses_mismatched_grids_with_structured_detail`,
  `test_compare_aligns_explicitly_and_records_provenance`,
  `test_compare_on_identical_grids_reports_no_resampling`,
  `test_compare_rejects_a_reference_that_is_not_one_of_the_scenes`.
- **Fusion** — `test_fusion_combines_two_sensors_and_keeps_per_source_records`,
  `test_fusion_rejects_raw_band_early_fusion`, `test_fusion_needs_at_least_two_distinct_sources`,
  `test_fusion_alignment_is_explicit_and_recorded`, `test_fusion_priority_rule_prefers_the_first_valid_source`,
  `test_fusion_rejects_negative_weights`.
- **Immutability / integrity** — `test_scene_analysis_is_immutable_and_listed`,
  `test_export_download_is_verified_and_matches_recorded_grid`,
  `test_tampered_export_is_refused_and_the_record_is_untouched`.

## Not verified / limits (stated, not glossed)

1. **No real satellite data was used.** Every number above comes from synthetic rasters.
   Nothing here claims accuracy of a water map on Sentinel-1/2 imagery; that needs
   independent reference data, which Phase 5 addresses.
2. **Geographic areas assume the source CRS is WGS84.** A geographic CRS on another
   ellipsoid would bias areas; the response records `ellipsoid: "WGS84 (assumed)"`.
3. **Patch-resolution scenes are classified per cell; areas are summed over each cell's
   true pixel window.** Cell area therefore equals the covered pixel count × pixel area,
   which is exact, but a cell's *class* represents its whole window (a modelling
   limitation inherited from the patch classifier, not an area bug).
4. **Alignment is nearest-neighbour only.** No bilinear/cubic option for categorical
   products (deliberate), and no reprojection-of-extent crop beyond what `rasterio.warp`
   does.
5. **Single-run classification only.** A scene can be classified repeatedly; each run is
   a new immutable record, but there is no bulk "classify all scenes" job or queue.
6. **Study-area inclusion rule is pixel-centre.** Boundary pixels are decided by centre
   containment; the rule is recorded but not user-configurable.
7. **Fusion writes only the fused hard map** (checked, checksummed). Fused probability
   and uncertainty products are returned in the record but not written as GeoTIFFs.
8. `vitest` suite covers adapter shaping for Phase 4 (10 new assertions); the Svelte
   components themselves are exercised via SSR smoke checks, not DOM unit tests.
