## Design

### 1. Run ordering and iteration ownership

Current: `list_runs` orders `ASC(iteration, id)`; `latest_run` orders `DESC(id)`;
the workspace assumes `runs[0]` is the latest; the client sends `iteration`.

Decision:

- `GET /projects/{id}/runs` returns **newest first**: `ORDER BY iteration DESC, id DESC`.
  This makes the list endpoint and `latest_run` agree, and makes the UI's
  `runs[0]` assumption correct by construction. The only known consumer is the
  workspace itself (plus Evaluation/Arena lists, which want newest-first anyway).
- `POST /train` **derives `iteration = max(iteration)+1` server-side** and
  ignores the payload value (kept optional in the schema for compatibility; a
  value that disagrees with the derived one is ignored, not an error, and the
  response always reports the derived iteration). This removes the duplicate-
  iteration class of bug permanently.
- The workspace keeps `latestRun = runs[0]` and stops computing iteration
  client-side (`state.train()` drops the `iteration` field).

### 2. Scene ↔ dataset linkage

Add `scenes.dataset_id` (FK → `datasets.id`, nullable, additive migration) and
`datasets.origin` (`String(10)`, `upload` | `scene`, default `upload`).

Backfill (one deterministic pass, idempotent):

- For each scene, the dataset row spawned at registration shares the scene's
  `content_sha256` and was created at the same moment (`uploaded_at` ≈
  `uploaded_at`); match on `(project_id, content_sha256)` and pick the dataset
  whose filename contains the acquisition separator " · " (scene display name
  format) when several share a digest.
- `origin='scene'` for linked rows; everything else stays `upload`.

`GET /scenes` (`SceneOut`) exposes `dataset_id`. The frontend `SceneView`
gains `datasetId: string | null`; `sceneRaster()` resolves the real dataset row
(keeping the synthetic fallback for rows deleted by donor removal).

### 3. Field loading is per active raster

`workspace.loadMapField(datasetId?: string)`:

- Resolves the raster: explicit id → else scene's `datasetId` → else
  `workspace.dataset.id`. The field cache key already includes the dataset id,
  so scenes and the training raster coexist in cache; the 8-entry cap is raised
  to 16 (four dates × layers realistically).
- The map page derives `fieldDataset = scene ? sceneDataset : workspace.dataset`
  and an `$effect` keyed on `(fieldDataset?.id, latestRun?.id)` loads the field
  whenever the date or run changes — replacing today's scattered manual calls.
  Hash navigation, project switches and raster-source changes all end in this
  effect; no other trigger sites are needed.
- Field provenance in the identity panel keeps coming from the field response
  (`iteration`, `resolution`), which is already authoritative.

### 4. Layer panel is stable across dates

The panel always lists: imagery, classification, uncertainty, samples, and
(binary only when the active run recorded a binary interpretation; threshold
only on scene views). For the classification/uncertainty entries:

- When a field exists for the active raster + latest run → toggle as today.
- When it does not → the row shows a muted "not classified for this date"
  state with a **Classify this date** action that calls `loadMapField` for the
  active raster; the toggle cannot be switched on while the field is missing.
- Switching dates with the layer enabled keeps it enabled and repaints from the
  new field; a raster whose bands cannot match the model (409/422) surfaces the
  existing schema-conflict alert scoped to that date, never a silent blank.

### 5. Pixel-granular queries

`POST /query` redesign around one rule: **the pool granularity follows the
latest checkpoint's resolution unless the request overrides it.**

- `QueryRequest.sample_resolution: 'patch' | 'pixel' | null` (null = follow the
  checkpoint; model-free strategies follow the latest checkpoint too, falling
  back to `patch` when none exists).
- Pixel pool: `make_grid(h, w, 1, stride)` where
  `stride = payload.stride or clamp(ceil(sqrt(h·w / 50_000)), 1, 8)`
  (bounded pool ≈ ≤50k candidates; recorded in `pool.stride`). Features come
  from `pixel_features(arr)` restricted to predictor bands (strict all-band
  validity); each candidate's window is 1×1 and `grid.coords` already yields
  the pixel centre.
- Patch pool: unchanged (`patch_features`, `patch_validity`).
- Scoring: pixel checkpoints predict on raw pixel vectors (width = bands),
  patch checkpoints on patch statistics (width = 4·bands); `uncertainty_scores`,
  `kcenter_greedy`, `select_hybrid` are granularity-agnostic. (SOM was removed
  from the product: it belonged to the legacy RSAL tool.)
- The 409 branch is deleted; the note instead states the granularity used and
  whether model scores were applied.
- Labels: `resolve_label_patches` maps points onto any grid via
  `_axis_index`, so pixel pools exclude labelled pixels with no new code.

Frontend:

- Pixel samples (window area ≤ 2 px) render a **context window**: clamp(
  center ± 32 px) for thumbnails, so the reviewer still sees surroundings.
- `Learning` sample meta shows "pixel" instead of the patch-size line when
  `window.x1 - window.x0 <= 2`.

### 6. Sample context map (Learning page)

New `SampleContextMap.svelte`, rendered in the review column above the label
panel (≈340 px tall, expandable):

- Imagery of the sample's own dataset (`renderRaster` true-color) + the
  classification field for that dataset (fetched through the same per-dataset
  field cache, opacity 0.55) + one pin per queue sample coloured by predicted
  class + a distinct target marker (ring + crosshair) on the focused sample.
- On focus change: `flyTo` the target (zoom 16 in map mode; a scale that shows
  ~40 px around the pixel in pixel-space mode) and drop the marker — the
  "overview → zoom → exact pixel" sequence the review flow needs.
- Clicking a pin calls `onpick(sampleId)` (same focus path as the list).
- Marker positions use `sample.geo` when the dataset is georeferenced,
  otherwise pixel-space y-flip, exactly like label markers today.
- Management stays in the label panel (change label = resubmit, delete, reject,
  defer) — the map and the list both drive the same focused sample, so
  "change/delete a sample from the samples layer" is: click pin → panel action.

### 7. Training hands off to the map

`workspace.train()` success path (after the run lands and fields are cleared):
if the operator is not already on the map view, `go('map')`; ensure
`map.layers.classification = true`; the map page's new field effect loads the
fresh field (cache key includes the new run id, so no stale hit). A notify
states that the new classification is being displayed. On the map page itself
the behaviour is identical without navigation.

### 8. Deterministic default dataset

`workspace.loadProject` picks `datasets.find(origin === 'upload')` (latest by
id) instead of `datasets.at(-1)`; `openRaster`/`selectDataset` keep explicit
selections. Falls back to the first dataset when a project has only scene
datasets (edge case: upload deleted).

### 9. Window-based sample placement

`showOnMap` and the map's selection highlight use the sample's recorded
`window`/`bbox` (true for any grid) instead of recomputing a cell from pool
`row/col` against the field grid. The uncertainty-field click path keeps
producing `{kind:'cell'}` selections with field-grid coordinates — both kinds
now coexist, each interpreted against its own grid.

### Compatibility / migration

- One additive Alembic-style migration (the engine's `alembic/` or its
  `CREATE TABLE IF NOT EXISTS`-style bootstrap — follow the existing pattern in
  `app/models.py` metadata setup); backfill runs in the same migration.
- Older clients that rely on ascending run lists: none in-repo; the CLI lists
  runs? No — `wbalc_cli.py` has no runs command. Safe.
- `QueryRequest.sample_resolution` is optional; existing clients get
  checkpoint-following behaviour with no request change.
- Patch checkpoints, patch queries, patch exports: byte-identical behaviour.

### Verification strategy

Backend: pytest for ordering (newest first), server-derived iteration (client
value ignored), scene dataset backfill, pixel-pool query (uncertainty + hybrid
+ diversity on a pixel checkpoint, pool.patch_size == 1, notes mention pixel
granularity), 1-px window coordinates. Frontend: vitest for context-window
math and layer-list stability; manual IAB pass on Zarivar: query → context map
zoom + marker → label → train (pixel, from the one-resolution bar) → auto map
handoff → switch dates (each date classifies independently) → identity panel
resolution badge truthful on every date.
