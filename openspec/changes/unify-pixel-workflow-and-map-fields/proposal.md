## Why

Field reports from real use (2026-11-21) show the pixel/patch split is not just
a feature gap — it produces contradictory products on screen and breaks the
active-learning loop. Auditing the live system against the code found one
critical ordering bug, two structural gaps, and four follow-on defects:

1. **The frontend tracks the wrong "latest run".** `GET /runs` returns runs
   ascending (`ORDER BY iteration, id`, `app/api/training.py:67`), but the
   workspace treats `runs[0]` as the latest model (`state.svelte.ts:163`). With
   runs `[1=patch iter0, 2=pixel iter1]` the UI believes the patch model is
   current while the engine predicts with the pixel one. Consequences: the next
   training request computes `iteration = 0 + 1` and **duplicates iteration 1**;
   the field cache key never changes across retrains; the arena compares the
   two oldest runs; run lists display oldest-first.
2. **Classification exists only for the training raster, never for a date.**
   The map page force-nulls every model-derived layer when a scene is selected
   (`Geospatial.svelte:99-104`) and filters classification/uncertainty/samples
   out of the layer panel. Scenes cannot be classified from the UI at all —
   yet the engine already accepts any dataset id in `GET /predict/map`. This is
   the reported "classification only appears at the right date by accident /
   after refresh".
3. **Scenes and their derived datasets are unlinked.** `POST /scenes` creates a
   queryable `Dataset` row per scene (`app/api/scenes.py:281`) but stores no
   reference in either direction, so the frontend cannot classify a scene (no
   dataset id) and cannot tell scene datasets from uploads. `workspace.dataset`
   defaults to `datasets.at(-1)` — silently the *newest scene dataset*, which is
   why the identity panel has been showing a 2-channel S1 raster while the
   operator believed they were looking at the 6-band training raster.
4. **Pixel checkpoints are second-class in active learning.** `POST /query`
   refuses uncertainty/hybrid for pixel checkpoints with a 409
   (`app/api/query.py:97-114`) because queries are hard-wired to patch
   embeddings. After a pixel run (the resolution the project has standardized
   on) the AL loop silently degrades or errors — the reported "two independent
   patch/pixel modes are confusing".
5. **The workspace trains patch models by default.** The Learning train bar
   defaults `resolution='patch'` (`Learning.svelte:43`), so one click after the
   pixel run reproduces a 320 m blocky map — the reported "the classified map
   is patch-sized, not pixel-sized".
6. **Proposed samples lack spatial context.** The AL review shows a windowed
   thumbnail and a colour swatch; there is no map, no zoom-to-sample and no
   marker on the exact target pixel, so the reviewer cannot tell *where* in the
   scene a suggestion sits (reported explicitly).
7. **Training gives no fast path to the result.** After a successful run the
   user must navigate to the map and coax the field into loading; the requested
   behaviour is that the fresh classification is visible immediately.
8. **Latent mismatches.** `showOnMap` places pool row/col against the *field*
   grid (wrong whenever the two grids differ); a pixel-mode sample's 1×1 window
   would render a 1-pixel thumbnail; the samples layer is map-page-only and
   offers no management from the review flow.

## What Changes

- **Run ordering is authoritative and newest-first.** `GET /runs` returns runs
  by descending iteration (ties by descending id); the engine derives
  `iteration` server-side (max + 1) and never trusts a client-supplied value
  for identity; the workspace's `latestRun = runs[0]` becomes correct.
- **Per-date classification.** Every `Scene` records the `Dataset` row it
  spawned (additive `scenes.dataset_id` + backfill via shared `content_sha256`),
  the map field loader is parameterised by the *active raster* (training raster
  or scene dataset), the layer panel always lists classification/uncertainty/
  samples with a "not classified yet" state plus a per-date classify action,
  and switching dates auto-loads that date's field from the per-dataset cache.
- **Pixel is the standard resolution.** The train bar exposes one resolution
  (pixel, 10 m) with patch available through the API only; hints and the
  resolution badge are updated to a single consistent story.
- **Pixel checkpoints drive active learning.** For pixel checkpoints the query
  pool becomes a pixel pool (`patch_size=1`, strict per-pixel validity, raw
  per-pixel predictor vectors): uncertainty/hybrid rank true pixel
  probabilities, diversity/hybrid diversify pixel spectra. Pool granularity is
  recorded in the batch (`pool.patch_size=1` + note), defaulting to the latest
  checkpoint's resolution and overridable via `sample_resolution`.
- **AL review gains a context map.** A dedicated sample-context map shows the
  sample's own dataset imagery with the classification field underneath, one
  pin per proposed sample (coloured by predicted class), and on focus flies to
  the target and drops a precise marker on the exact pixel/cell; clicking a pin
  focuses that sample. Pixel samples render a context window (±32 px) instead
  of a 1-pixel thumbnail.
- **Training hands off to the map.** A successful run enables the
  classification layer, navigates to the map, and loads the fresh field (the
  cache is already invalidated per run).
- **Default dataset is deterministic.** `Dataset` rows gain an `origin`
  (`upload` | `scene`, backfilled by digest match); the workspace defaults to
  the project's upload/training raster, never to whichever scene registered
  last.
- **Sample placement is grid-honest.** `showOnMap` and the selection highlight
  use the sample's recorded pixel window (`window`/`bbox`), which is correct
  for any grid, instead of reinterpreting pool row/col against the field grid.

## Capabilities

### Modified Capabilities
- `model-training` — run listing order and server-derived iteration.
- `map-overlays` — classification/uncertainty are per-active-raster (scenes
  included), always listed, with an explicit unclassified state.
- `active-learning-query` — pixel checkpoints produce pixel-granular batches
  instead of a 409; granularity is recorded.
- `frontend-workspace` — single-resolution train bar, after-training map
  handoff, AL context map with zoom + target marker and sample management,
  per-date field loading, deterministic default dataset, window-based sample
  placement, pixel-sample thumbnails.
- `scene-library` — each scene records the dataset row it spawned
  (`dataset_id`, backfilled by digest) so dates can be classified.

## Impact

- **Backend:** `app/api/training.py` (ordering, iteration), `app/models.py` +
  additive migration (`scenes.dataset_id`, `datasets.origin`), `app/api/scenes.py`
  (link + expose), `app/api/query.py` (pixel pool, granularity notes),
  `app/api/deps.py` unchanged, `app/schemas.py` (SceneOut.datasetId,
  QueryRequest.sample_resolution).
- **Frontend:** `state.svelte.ts` (latestRun semantics, loadMapField(datasetId),
  train handoff, default dataset), `Learning.svelte` (train bar, context map,
  thumbnails), new `SampleContextMap.svelte`, `Geospatial.svelte` (layer panel,
  field effects, provenance), `types.ts`/`client/api.ts` (datasetId,
  sample_resolution), i18n en/fa.
- **Data:** one additive migration, backfilled deterministically; no source
  files touched; existing checkpoints remain valid (patch workflow unchanged
  server-side).
- **Tests:** engine tests for ordering/iteration/pixel-pool queries; frontend
  tests for context-window math, context-map focus behaviour, and layer-list
  stability across date switches; one live end-to-end pass on the Zarivar
  project (query → label → train pixel → map on three dates).

## Non-goals

No new fusion strategy, no S1/S2 feature fusion, no change to patch checkpoints'
predict/export semantics, no reimplementation of the queue persistence, no new
map basemap, no deletion of batch history or labels beyond existing endpoints,
no automatic retraining triggers, and no reprojection or resampling of any
raster.
