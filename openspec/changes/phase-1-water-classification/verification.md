# Verification — phase-1-water-classification

Date: 2026-11-18. Branch: `arena/a4a6bd6b-wbalc`.
Executed in this workspace. Everything below was run; nothing is described as
verified unless the command actually produced the quoted result.

## What shipped

### Taxonomy (versioned, explicit)

- `app/services/taxonomy_service.py`: `TAXONOMY_VERSION = "wbalc-water-taxonomy-v1"`,
  ordered `INTERNAL_CLASSES = [open_water, emergent_vegetation, land]`,
  `build_taxonomy(...)` producing a serialisable snapshot (version, class order,
  display names, aliases, **crosswalk**, binary interpretation, source).
- A class ID is always its own alias, so an unconfigured project still resolves
  `open_water`. Nothing else is assumed — in particular **`reed` is not a default
  alias**; it exists only when the project configures it.
- Ambiguous aliases (one term → two classes), unknown canonical names and
  non-string aliases are rejected (`TaxonomyError` → HTTP 422).
- Persisted via additive migration **v003** (`projects.taxonomy` JSON). `NULL`
  means "generic/legacy project, no water crosswalk", never backfilled.
- `GET /projects/{id}/taxonomy` returns the computed description, including which
  binary product is available and why.
- `ProjectCreate` now refuses a class list that is neither the water taxonomy nor
  an explicit `generic_classes: true` opt-out — this is what makes "a WBALC
  project" mean something instead of being implied.

### Label crosswalk

- `app/api/labels.py::_resolve_class_name` resolves submitted text through the
  project's crosswalk. Unknown text is a 422 that names the project's classes and,
  when a similar alias exists, the closest configured classes. Nothing is coerced.
- The submitted text is preserved: additive migration **v004** adds
  `labels.submitted_class_name`, filled only when it differs from the resolved
  class. History is never rewritten.
- The frontend's GeoJSON import route now uses the same crosswalk instead of a
  plain "is it in `classes`" check, and its message says "has no mapping in this
  project's taxonomy".

### Products

- The three-class hard/probability/uncertainty product is unchanged and stays the
  source of truth (`/download/hard`, `/download/probability`).
- New derived products: `/download/binary` (1 = water, 0 = other, NoData
  preserved) and `/download/binary_probability` (P(water), bounded 0..1), for both
  pixel and patch-cell grids. Exports are registered as `binary` /
  `binary_probability` with the same stale-detection as the others.
- `GET /predict/map?layer=binary` returns the derived field for the map, with
  classes `["non_water", "water"]`. The three-class `layer=hard` response is
  unaffected.
- Exact mappings, from `BINARY_MAPPINGS`:
  - `water_vs_non_water`: open_water + emergent_vegetation → water, land → other.
  - `open_water_vs_other`: open_water → water, emergent_vegetation + land → other.
- **Absent classes are reported, not synthesized.** Additive migration **v005**
  records `training_runs.trained_classes`; the derived-plan is computed over the
  learned subset, so a model that never saw `emergent_vegetation` reports
  `available: false`, names the missing class and explains it. No binary file is
  written and no `binary` link is advertised.
- GeoTIFFs carry `derived=true`, `interpretation`, `mapping`, `source_classes`,
  `source_training_run_id`, `taxonomy_version`, and a description stating that the
  three-class map is the source product.
- Runs and checkpoints snapshot the taxonomy (`params["taxonomy"]`,
  checkpoint `taxonomy`). A project config change after training does **not**
  reinterpret an existing run — the test asserts the historical mapping survives.

### UI

- Adapter: `ProjectView.taxonomy` (version/source/classes/displayNames/aliases),
  `classificationConfig.labelAliases`, `MapFieldView.binary` (`BinaryView`).
- Geospatial page: a *Classifier classes* panel that distinguishes the internal
  water taxonomy from the project's generic class list, shows the derived binary
  interpretation and its mapping, and says why it is unavailable when it is; a
  *Water (derived)* map layer with its own legend colours (`BINARY_COLORS`,
  deliberately not the class palette), only offered when the run recorded an
  interpretation; "Export view" exports the derived product when that layer is on.
- i18n: 355 keys in `en` and `fa` (was 340), 0 drift.

## Commands and results

```
$ .venv/bin/python -m pytest
217 passed, 1857 warnings in 57.29s
```
(194 after Phase 0 → 217 now; 23 new tests in
`tests/test_water_classification_phase1.py`.)

```
$ npx svelte-check --tsconfig ./tsconfig.json
svelte-check found 0 errors and 0 warnings

$ npx vitest run
Test Files  5 passed (5)
     Tests  52 passed (52)

$ node scripts/check-i18n.mjs
✔ i18n complete: 355 keys in en.ts and fa.ts

$ npx vite build
✔ done            (adapter-node)
```

```
$ .venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
75 checks passed
```
New end-to-end checks: the taxonomy snapshot is on the project view; the taxonomy
endpoint reports the binary plan; `map-field?layer=binary` returns
`classes: ["non_water","water"]` with its mapping; `/exports?type=binary` streams a
categorical GeoTIFF whose `derived`/`interpretation` tags match the run.

## Not verified / deliberately open

- **No area calculation, change detection or accuracy claim.** Phase 4 owns
  temporal/area products; this change only defines class semantics and the derived
  binary product.
- **Emergency reeds are a domain judgement.** The software exposes the alias
  mechanism and refuses unmapped terms; it does not assert that emergent
  vegetation equals reeds, and the UI copy says so. Whether a given alias is
  scientifically right is the operator's call, recorded in the project's config.
- **Legacy runs keep their behaviour.** Runs created before this change have no
  taxonomy snapshot and no `trained_classes`; they produce no derived binary
  product (`binary: null`, `layer=binary` → 409 with an explanation) rather than a
  guessed interpretation. `trained_classes = NULL` is read as "the full class
  list", which is the pre-Phase-1 assumption.
- **Manual visual check** of the new legend/panel is still a human task (Playwright
  cannot be installed here); type-checking, adapter tests and the smoke run are the
  automated evidence.
- **Patch-mode binary product** is painted per cell over its pixel window, exactly
  like the three-class patch map — it is not a per-pixel water mask.
