# Phase 5 verification — research evaluation protocols, benchmarks and reporting

Change: `phase-5-research-evaluation`
Branch: `arena/a4a6bd6b-wbalc`
Verification date: 2026-11-19 (sandbox clock) — synthetic data only.

## What shipped

### Backend

| Area | Implementation |
| --- | --- |
| Protocol records | `EvaluationProtocol` + migration **v009** (`app/migrations/v009_research.py`, additive, five tables, `checkfirst=True`). Stores protocol kind, seed, full split membership, held-out groups, configuration, `split_hash` (sha256 over the canonical split) and an explicit `status` + `reason`. |
| Split engine | `app/services/protocol_service.py`. `random` = seeded stratified holdout; `spatial` = block holdout keyed **per dataset** (`block:{dataset_id}:{row}:{col}`) with a per-dataset buffer reach; `temporal` = whole acquisition-group holdout. Zero train/test group overlap is asserted, not assumed. |
| Insufficiency | A split the data cannot support is **stored as `insufficient` with a reason** rather than being forced or silently downgraded to a random split. |
| Held-out scoring | `app/services/research_service.py::score_protocol` (async) refits a fresh model on the training partition, scores only the held-out partition, records `metrics.dropped`, and saves an evaluation-scoped checkpoint. The production model is never re-used, because it has seen every labelled sample. |
| Class metrics | `app/services/metrics_service.py`: stable class order, per-class support/predicted, and **null + per-metric reason** for anything undefined (e.g. precision with no predicted positives). A null never becomes 1.0. Balanced accuracy lists which classes contributed. |
| Calibration / coverage | Equal-width ECE, maximum CE, Brier and a coverage curve, each with `n_samples`, method and a "held-out only" caveat; `available: false` + reason when there are no held-out predictions. |
| Area error | `ReferenceArea` records operator-supplied truth (area + source + method + optional uncertainty, `GET/POST .../reference-areas`). `GET .../area-error` answers **409** until both a reference area *and* a classified scene exist. The engine's own map is never used as truth. |
| Scene spread | `GET .../scene-spread` aggregates per-scene values, refuses to pool pixels (409 "nothing to aggregate") and reports the resampling unit. |
| AL / plan comparisons | `ResearchPlan` declares factors, levels, repetitions, comparison metric and holdout protocol **before** runs. `POST .../plans/compare` returns `shared`/`differing` factors, per-result values and a `paired` verdict — `false` whenever the results were not scored on the same persisted split, in which case the response says so in `caveats`. |
| Report bundle | `app/services/report_service.py`: JSON + CSV + Markdown from stored Phase 3/4/5 records, each artifact with `sha256` + `size_bytes`, plus a canonical `digest`. `_canonical` strips `generated_at`/`created_at`/`path`/`storage_reference` **and coerces `datetime`/`date`/`Decimal`/numpy scalars** to JSON-native values, so regeneration hashes equally and the bundle can be stored in a JSON column. |
| Download integrity | `GET .../reports/{id}/files/{kind}` re-verifies the stored checksum before streaming; a tampered file → `409` and the record is untouched. |
| Software vs science | `GET .../status` returns `software_validation` (tests on synthetic data) next to `scientific_validity: "not established"`, with counts and a plain-language detail paragraph. The distinction is in the payload, not only in the docs. |
| Project cascade | Phase 3–5 tables only carried a `project_id` FK, so `DELETE /projects/{id}` left orphans. `Project` now declares `cascade="all, delete-orphan"` for `scene_analyses`, `fusion_runs` and the five research tables; migration **v010** (`app/migrations/v010_project_cascades.py`) records the change. Proven by a test that fails without the cascade. |

### Frontend

- `Evaluation.svelte` gains a research panel: scientific status split into software validation vs scientific validity, protocol declaration (kind, seed, block size, buffer), protocol table with train/test counts, split hash and the insufficiency reason, a "score held-out split" action, result cards with per-class support + null-with-reason rows, calibration/coverage, dropped-sample counts, reference-area entry (area, source, method — both provenance fields mandatory), plan creation + comparison with the pairing verdict and differing factors, and the report bundle with digest, per-artifact download links and stated limitations.
- Adapter: `toProtocol`, `toEvaluationResult`, `toReferenceArea`, `toResearchPlan`, `toPlanComparison`, `toReport`, `toScientificStatus`; routes under `/api/projects/{id}/research/{protocols,evaluations,reference-areas,plans,plans/compare,reports,reports/{reportId}/files/{kind},status}`.
- Client-side validation errors are `ApiError(…, 400)`, so a bad form answers **400**, not a 500 from an unhandled `Error`.
- i18n: **547 keys** in `en.ts` and `fa.ts` (was 487).

## Commands actually run

```
.venv/bin/python -m pytest -p no:warnings                    # 334 passed in 107.84s
.venv/bin/python -m pytest tests/test_research_phase5.py -q   # 33 passed
cd examples/wbalc-geospatial-research-interface
npx svelte-check --tsconfig ./tsconfig.json                  # 0 errors, 0 warnings
npx vitest run                                               # 5 files, 78 tests passed
node scripts/check-i18n.mjs                                  # 547 keys in en.ts and fa.ts
npx vite build                                               # adapter-node, done
.venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
                                                             # 140 checks passed
```

`tests/test_scenes_api.py` migration assertion now expects versions 1…10.

## Coverage of the spec's acceptance themes

All 33 tests live in `tests/test_research_phase5.py`; names below are verbatim.

- **Leakage-safe, reproducible protocols** — `test_random_split_is_deterministic_and_disjoint`,
  `test_protocol_endpoint_persists_membership_and_hash`,
  `test_spatial_split_holds_out_whole_blocks_and_never_shares_one`,
  `test_spatial_buffer_removes_neighbouring_blocks_from_training`,
  `test_spatial_split_refuses_when_blocks_are_too_few`,
  `test_temporal_split_holds_out_whole_acquisitions`,
  `test_temporal_split_refuses_with_a_single_acquisition`,
  `test_temporal_protocol_holds_out_a_whole_dataset`,
  `test_protocol_refuses_a_split_the_data_cannot_support`,
  `test_unknown_protocol_and_bad_parameters_are_refused`.
- **Held-out scoring only** — `test_evaluation_scores_only_the_held_out_partition`,
  `test_empty_project_reports_insufficient_rather_than_failing`,
  `test_summarize_flags_an_empty_held_out_set`.
- **Null/reason metric semantics** — `test_per_class_metrics_report_nulls_with_reasons`,
  `test_precision_is_undefined_when_a_class_is_never_predicted`,
  `test_macro_average_excludes_undefined_classes_and_says_so`,
  `test_balanced_accuracy_counts_only_reference_classes`.
- **Calibration / coverage** — `test_calibration_and_coverage_need_samples_and_report_counts`.
- **Independent reference area** — `test_area_error_requires_a_reference_and_a_classified_scene`,
  `test_area_error_requires_a_reference_and_reports_units`.
- **Aggregation unit** — `test_scene_spread_refuses_to_pool_pixels_without_scenes`,
  `test_scene_distribution_uses_scenes_as_the_independent_unit`,
  `test_sample_records_keep_the_acquisition_group_and_drop_non_points`.
- **Plan/ablation control** — `test_plans_record_factors_and_refuse_a_fake_paired_comparison`.
- **Report bundle** — `test_report_bundle_is_generated_with_three_artifacts_and_a_digest`,
  `test_bundle_digest_is_stable_across_regeneration`,
  `test_bundle_excludes_legacy_runs_and_names_why`,
  `test_csv_lists_one_row_per_class_metric`,
  `test_markdown_states_absent_reference_data_and_undefined_metrics`,
  `test_tampered_report_artifact_is_refused`,
  `test_report_bundle_with_no_results_says_so`.
- **Honesty surfaces** — `test_scientific_status_separates_software_from_science`.
- **Migrations / cascade** — `test_deleting_a_project_removes_its_research_records`,
  `tests/test_scenes_api.py` migration version tuple 1…10.

## Not verified / limits (stated, not glossed)

1. **No real satellite imagery and no real reference area exist in this repository.**
   Every number was produced from synthetic 64×64 rasters and synthetic labels. No
   accuracy, calibration or area-error figure here is evidence about water mapping.
   `scientific_validity` is `"not established"` for that reason, in the API itself.
2. **Area error has never been computed on real data** — the endpoint and its guards are
   tested, but the only reference areas are operator-entered values in tests.
3. **Temporal holdout resolution is the acquisition group.** Groups come from the dataset
   id or an explicit `group_map`; there is no dataset→scene foreign key, so a caller that
   declares neither gets one group per dataset.
4. **Spatial blocking is axis-aligned on the raster grid**, not geodesic. Block and buffer
   are in pixels, and the CRS/units are documented in `configuration` rather than
   reprojected.
5. **`paired` is a structural claim, not a statistical one.** It asserts the results were
   scored on the same persisted split; it does not run a significance test, and no p-value
   or confidence interval is produced.
6. **Report regeneration is stable within a database, not across databases.** Ids and
   storage paths are part of the bundle, so two projects with identical content but
   different ids produce different digests.
7. **CSV is a flattened metrics view**, not a full relational export; the JSON bundle is
   the authoritative artifact.
8. **No HTML artifact.** Markdown ships; converting it to HTML is left to the consumer.
9. **Frontend DOM tests are shallow.** `vitest` covers adapter shaping (9 new assertions);
   the research panel itself is exercised through SSR smoke checks against a live engine.
