# Verification — harden-pixel-classification-contract (Phase 0)

Date: 2026-11-18. Branch: `arena/a4a6bd6b-wbalc` (from `53047b8`).
All evidence below was executed in this workspace. Nothing is simulated; items that
require a human or a capability the engine does not have are listed as **not
verified** instead of being ticked.

## What shipped

### Backend

| Area | Change |
| --- | --- |
| Explicit reference raster | `PredictRequest.dataset_id` is required (`Field(ge=1)`); the "latest dataset" fallback is gone from `POST /predict`. `require_dataset` still resolves the optional query for map/export endpoints, but every response names the dataset it used. |
| Provenance | `PredictResponse` / `MapFieldOut` carry `training_run_id`, `band_schema_verified`, `band_schema_reason`, `schema_override`, `study_area_applied`, `study_area_note`. GeoTIFFs carry the same as GDAL tags. |
| Band identity | `app/services/schema_service.py`: `build_band_schema`, `schema_digest` (sha256 over version + ordered names + count, 32 hex), `compare_schemas` → `(verified, reason)`. Declared only when *every* band is named. |
| Training contract | `_verify_training_schemas` in `pipeline.py` refuses mixed/undeclared/mismatched-count inputs (`SchemaConflict` → **422**) unless `accept_unverified_schema` is set, in which case `schema_override` is recorded on the run. |
| Checkpoints | `save_checkpoint(..., band_schema=...)`; `resolve_inference_contract` compares the checkpoint's schema with the selected raster and 409s with a named reason. |
| Study-area mask | `app/services/mask_service.py`: vector-only CRS transform (`rasterio.warp.transform`) + numpy pixel-centre scanline fill (even-odd, holes honoured), down-sampled to patch cells when needed. `hard→0`, `prob→0`, `unc→0`, `valid=False` outside; nothing is resampled. Missing CRS / bad geometry → **422** `Study area cannot be applied: …`. |
| Migration | `v002_dataset_band_schema.py` — additive `ALTER TABLE datasets ADD COLUMN band_schema JSON`, registered as version 2. `NULL` = undeclared, never guessed. |
| Resource bounds | `check_element_budget` in `raster_service.py`, used by inference (× classes for per-pixel), patch loading and pixel training extraction. Refusal is pre-allocation and actionable. |

Dependency note: no new runtime dependency. `shapely` was installed to prototype and
then **uninstalled**; masking uses numpy + `rasterio.warp.transform` only.

### Frontend (`examples/wbalc-geospatial-research-interface`)

- `map-field`, `exports` and `train` adapter routes forward
  `accept_unverified_schema`; a 409/422 from the engine is relayed verbatim.
- `MapFieldView` gained `bandSchemaVerified`, `bandSchemaReason`,
  `studyAreaApplied`, `studyAreaNote`; `DatasetView` gained `bandNames`,
  `bandSchemaDeclared`, `sensor`. Missing fields from an older engine default to
  "unverified", never to "verified".
- Workspace state: `schemaOverride` (reset on dataset/project change, part of the
  field cache key), `fieldErrorStatus`, `acceptSchemaOverride()`.
- Geospatial page: a provenance panel (model iteration, grid resolution,
  study-area decision, reason), band list with an explicit *Undeclared (unnamed
  bands)* state, and — on a 409 — an *accept override* action instead of a bare
  retry.
- Learning page: the schema refusal is named separately from other training
  failures, with an explicit **accept unverified band schema** checkbox.
- The previous, now-false UI claim that the engine "does not yet clip predictions
  to the study area" was removed from both dictionaries and replaced by a
  description of what actually happens.
- i18n: 340 keys in `en` and `fa` (was 325), 0 drift.

## Commands and results

### Backend

```
$ .venv/bin/python -m pytest
194 passed, 1576 warnings in 52.44s
```

Baseline before this change was 171 passed. The 23 new tests live in
`tests/test_pixel_contract_phase0.py` (18 at first, +5 for resource bounds,
immutability and resolution parity) and cover:

- 101×73 patch case (grid 10×13, export reopens at 73×101 with the source affine)
  and 101×73 pixel mode (grid 73×101, export 73×101);
- 7×11 rotated / non-square-pixel affine round-trip;
- explicit `dataset_id` required; foreign dataset → 404;
- same-count reordered bands → 409 with `ordered band names differ`; identical
  ordered names → verified;
- undeclared schema: training 422 → accepted with override → predict 409 →
  accepted with override and flagged `schema_override: true`;
- mixed schemas across two datasets → 422, accepted with override;
- study area: polygon half-raster masks hard/prob/unc/valid and the GeoTIFF
  (`nodata` outside, `study_area_applied` tag), WGS84 polygon projected into
  UTM-31N selects a strict subset, missing CRS → 422;
- unit tests for `compare_schemas` (order matters, undeclared never verifies) and
  for the mask (point geometry rejected, no-CRS rejected, polygon selects the
  expected half);
- pre-allocation element budget with the exact refusal text;
- source raster byte-identical after predict + all three exports;
- patch vs pixel products distinguished (8×8 vs 64×64 grid, distinct run ids,
  map field follows the newer run);
- partial-window export keeps the window dimensions and offset.

### Frontend

```
$ npx svelte-check --tsconfig ./tsconfig.json
svelte-check found 0 errors and 0 warnings

$ npx vitest run
Test Files  5 passed (5)
     Tests  47 passed (47)

$ node scripts/check-i18n.mjs
✔ i18n complete: 340 keys in en.ts and fa.ts

$ npx vite build
✓ built in 17.68s
✔ done            (adapter-node)
```

New frontend tests: `src/lib/contract.test.ts` (7 tests) — declared vs undeclared
band identity, a missing `band_schema` from an older engine treated as undeclared,
schema verdict and study-area flag carried through, and an engine that stays
silent never being read as "verified" or "masked".

### End-to-end smoke (live engine + live dev server)

```
$ .venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
69 checks passed
```

New checks in that run: the dataset view reports its declared band schema; the
hard map field reports provenance (`bandSchemaVerified: true`,
`studyAreaApplied: false`, `trainingRunId` matching the run); an undeclared
raster is reported as undeclared rather than guessed; a map field on it is
refused with a relayed 409 mentioning `accept_unverified_schema`; and the same
request with the override produces a product flagged `bandSchemaVerified: false`.

## Not verified / deliberately open

- **Task 6.3 — manual QGIS overlay check: not done.** It needs a human in a GIS
  application. `tasks.md` keeps it unticked on purpose. The automated substitutes
  (exact affine/dimension checks, NoData assertions, rotated-affine round-trip)
  are recorded above; they are not the same evidence.
- **Playwright / visual check** is still not possible in this sandbox (install
  fails), so the new provenance panel, override button and training checkbox have
  no automated browser assertion beyond type-checking and the DOM component tests
  already present.
- **No streaming / out-of-core inference.** The probability cube for the
  requested window is still materialised. `MAX_RASTER_ELEMENTS` now counts it
  (× classes) and refuses before allocating, and both README and the UI say so.
  This is the design's accepted option, not a claim of streaming.
- **Patch-mode masking is at cell resolution.** A cell is inside when its centre
  is inside the polygon; the products say `study_area_applied` with a note, and
  the README documents it. It is not a per-pixel clip of a patch product.
- **`sensor` is optional corroboration.** Two datasets that both name their bands
  verify even when one omits the sensor; when both declare one and they differ,
  the comparison fails. This is deliberate (a missing label does not weaken a
  proven ordered band list) and is what the tests assert.
