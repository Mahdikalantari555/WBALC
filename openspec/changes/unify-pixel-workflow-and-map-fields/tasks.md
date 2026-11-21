## Tasks

### 1. Run ordering and iteration ownership (backend)
- [x] 1.1 `list_runs`: order `iteration DESC, id DESC`; update/extend tests asserting newest-first.
- [x] 1.2 `run_training`: derive `iteration = max(existing)+1` server-side; ignore the payload value; response reports the derived iteration; test that two consecutive trains produce iterations N+1, N+2 even when the client repeats one.
- [x] 1.3 Frontend `state.train()` stops sending `iteration`; `Evaluation`/run lists render newest-first without re-sorting.

### 2. Scene ↔ dataset linkage (backend + migration)
- [x] 2.1 Additive migration: `scenes.dataset_id` (nullable FK), `datasets.origin` (`upload`|`scene`, default `upload`).
- [x] 2.2 Backfill: link each scene to the dataset row sharing its `content_sha256` (prefer filename containing the " · " display separator) and set `origin='scene'`; idempotent.
- [x] 2.3 `POST /scenes` writes `dataset_id` on the scene and `origin='scene'` on the dataset row; `GET /scenes` exposes `dataset_id` (schema + response model).
- [x] 2.4 Donor-removal / dataset deletion paths keep the link honest (null it when the dataset row is deleted).
- [x] 2.5 Tests: registration links scene↔dataset; backfill matches a legacy project; SceneOut carries `dataset_id`.

### 3. Per-date map fields (frontend)
- [x] 3.1 `state.loadMapField(datasetId?)` resolves scene → `datasetId` → training raster; cache cap 8 → 16.
- [x] 3.2 `SceneView.datasetId` + `sceneRaster()` resolves the real dataset row (synthetic fallback kept).
- [x] 3.3 Map page: single `$effect` on `(activeDatasetId, latestRunId)` loads fields; delete the scattered manual trigger sites it replaces.
- [x] 3.4 Layer panel: classification/uncertainty/samples always listed on every raster view (scene or training); binary keeps its availability gate; threshold keeps its scene gate.
- [x] 3.5 Unclassified state: muted row + "Classify this date" action when no field exists for the active raster+run; toggle disabled until a field arrives.
- [x] 3.6 Schema conflict for a specific date surfaces the existing conflict alert scoped to that date (no stale cross-date error text).
- [ ] 3.7 vitest: layer-list stability across date switches; effect triggers on run/date change.

### 4. Pixel-standard training UX (frontend + i18n)
- [x] 4.1 Learning train bar: single resolution (pixel) — remove the patch option from the UI, keep `workspace.train` API signature; hints describe "prediction grid = source pixels (10 m)".
- [x] 4.2 Resolution badge/hints across map + learning pages state one consistent story; i18n en/fa updated (drop patch-only keys where unused).

### 5. Pixel-granular queries (backend)
- [x] 5.1 `QueryRequest.sample_resolution` (`patch`|`pixel`|null); pool granularity follows the latest checkpoint's resolution unless overridden.
- [x] 5.2 Pixel pool: `make_grid(h, w, 1, stride)` with bounded stride (≤ ~50k candidates, formula in design §5); `pixel_features` on predictor bands; strict validity; delete the pixel-checkpoint 409 branch.
- [x] 5.3 Batch provenance: `pool.patch_size=1` for pixel pools + note naming the granularity and whether model scores were used; `QueryPoolOut` unchanged shape.
- [ ] 5.4 Uncertainty/hybrid/diversity verified on pixel checkpoints (unit test with a tiny pixel-trained checkpoint: scores, kcenter, hybrid all return valid picks; labelled pixels excluded). SOM was removed from the product (legacy RSAL feature).
- [x] 5.5 Patch-checkpoint behaviour byte-identical (existing tests pass unchanged).

### 6. Sample context map + management (frontend)
- [x] 6.1 Context-window helper: pixel windows ≤2 px expand to ±32 px (clamped); unit test the math.
- [x] 6.2 `SampleContextMap.svelte`: imagery + classification of the sample's dataset (per-dataset field cache), queue pins coloured by prediction, target marker on focus, fly-to on focus change, pin click → focus.
- [x] 6.3 Integrate into Learning review column; sample meta shows "pixel" for 1-px windows.
- [x] 6.4 Samples management via map: pin click focuses the same sample the panel acts on (change label / delete / reject / defer unchanged, now reachable from the map).
- [x] 6.5 `showOnMap`/selection highlight use the sample's recorded `window`/`bbox` (grid-honest for any pool).
- [ ] 6.6 vitest: context map focus behaviour (marker lat/lng from `sample.geo`), pin pick wiring.

### 7. Training → map handoff (frontend)
- [x] 7.1 `workspace.train()` success: enable classification layer, navigate to map when elsewhere, notify; map effect loads the new run's field.
- [ ] 7.2 Manual e2e on Zarivar: train from Learning → map shows fresh pixel field without any manual refresh.

### 8. Deterministic default dataset (frontend)
- [x] 8.1 `loadProject` defaults to the latest `origin='upload'` dataset (fallback: first dataset); `DatasetView.origin` typed.
- [x] 8.2 Identity panel dataset badge truthful (6-band training raster by default, 2-band only when an S1 scene is actually selected).

### 9. End-to-end verification
- [x] 9.1 Full backend suite green for touched files (ordering, query, scenes, training).
- [x] 9.2 `svelte-check` + frontend build green.
- [x] 9.3 Live pass on project 4: per-date classification on ≥3 dates, pixel query batch → context-map review → label → pixel train → immediate map, arena/evaluation unaffected.

### 10. Manual samples from the map (added 2026-11-21, delta `specs/label-management/`)
- [x] 10.1 Probe-to-label form in the map selection panel: class chips from the project taxonomy, existing-label revision note, per-dataset gate (synthetic scene views explain why they cannot host labels).
- [x] 10.2 `POST /labels` accepts id-less pixel labels (`sample_resolution: 'pixel'`), so the engine derives the stable `d{id}_p{row}_c{col}` identity and re-labeling a pixel revises the same sample; queue labels now record their true pool granularity too.
- [x] 10.3 Verified live on project 4: a probed lake pixel became manual sample `d2_p485_c175` (open_water) and the samples layer picked it up without a reload.
