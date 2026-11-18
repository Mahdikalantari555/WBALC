## Context

The merge under test (`d865c82`) already establishes the pixel path end to end.
This change repairs the integration seams the audit found: export geometry, mask
consistency, checkpoint trust, query/SOM input hygiene, and the API/frontend
contract. No new algorithm, no new endpoint, no removed field.

## Decisions

### 1. Patch exports are painted on the source grid

`make_grid` clamps the last row/column, so cell windows are not a uniform stride
lattice. A single affine transform cannot describe clamped cells, and both
alternatives are wrong:

- *Lattice export with cell values* (current): the last cell is painted where the
  lattice puts it, up to one stride away from its true window, and the raster
  extends past the source extent.
- *Uniform non-clamped grid*: the final `< stride` strip of the scene is silently
  left unclassified, which is worse than a documented `nodata` gap.

Chosen: **paint each cell's value over its true pixel window on the source grid**
(row/column ranges from the same `PatchGrid` the map and CSV use). The result has
the region's exact dimensions, CRS, affine and bounds; uncovered pixels (only
possible when `stride > patch_size`) are nodata. Values are replicated, never
interpolated, so categorical semantics hold. This is a *block-filled patch map*,
not per-pixel classification, and the `resolution` tag says `patch-cells`.
Pixel mode is unchanged: one class per source pixel.

Writes are streamed cell-row by cell-row (`Window` writes), so memory stays at
`classes × patch_height × width` floats instead of a full probability cube, and
each artifact is written to `<name>.tmp` then `os.replace`d before validation.

### 2. Validity is a property of the probability tensor, not of the renderer

`maps_from_inference` already masked hard and uncertainty. Probabilities are now
masked with `NaN` at the same cells; `POST /predict` serialises them as `null`.
The invariant: **for any invalid cell, hard == NODATA, probability == null,
uncertainty == null, valid == false**, for both resolutions.

### 3. Checkpoints declare their feature schema

`save_checkpoint` writes `feature_schema` (`pixel-band-vector` |
`patch-band-stats`) and `n_features`, keeps `resolution`, `bands`, `classes`,
`iteration`, `patch_size`, `stride`, and bumps `format` to `rsal-checkpoint-v2`.
`load_checkpoint` validates keys and types and checks `model.classes_` against
the stored class list (order is index → class name, so drift corrupts labels).
Legacy `rsal-checkpoint-v1` payloads are accepted **only** as patch checkpoints
(their historical meaning) and carry `legacy=True`, which the API surfaces.

Callers that build features themselves (query, SOM explorer, inference) assert
`resolution` matches the feature family they computed; a mismatch is a 409 with
an actionable message, never a silent reinterpretation.

### 4. Query degrades explicitly, never silently

- `uncertainty` / `hybrid` with a non-patch checkpoint → 409: the query grid is
  the patch grid; ranking needs a patch-feature model.
- `diversity` / `som` are model-free. With a pixel checkpoint they still run,
  return `model_iteration: null` and put a human-readable string in `notes`.
- Invalid patches are removed from the candidate pool before scoring, so
  `batch_size` can legitimately return fewer samples; the response already
  reports the realised count.

### 5. SOM ignores incompatible models and invalid observations

The explorer overlays predictions when (and only when) the checkpoint is a patch
checkpoint with matching bands; otherwise `model_iteration` is null and a note
explains why. Invalid patches are excluded from the fit, from `hit_grid`, from
cell `sample_ids`, and from `labeled_patches`. `total_patches` keeps its meaning
(all grid cells) and `valid_patches`/`nodata_patches` are added.

Pixel-mode SOM validity becomes `np.isfinite(...).all(axis=1)` — identical to
supervised pixel mode — so a pixel missing a band is nodata rather than being
imputed into a cluster.

### 6. Downloads are never stale without disclosure

`GET /download/{type}` regenerates when the newest export of that type predates
the latest run (the same predicate `/exports` already exposes as `stale`), and
always sets `X-RSAL-Model-Iteration` and `X-RSAL-Export-Stale` headers. SOM
exports have no run association and are unchanged.

### 7. Alternatives rejected

- Rejecting rotated grids on export: rejected. No endpoint resamples, so copying
  the source affine is exact for rotated rasters too; the frontend preview
  limitation is documented instead.
- Major dependency upgrades: rejected (`npm audit fix --force` downgrades deck.gl
  and breaks the workspace).
- Adding a persistent query-batch store: rejected. The review queue is already
  persisted in `localStorage` (zustand `persist`), so there is no confirmed
  label-loss defect; the README now states the behaviour and its limits.

## Risks

- Patch GeoTIFFs become region-sized; a project that scripted the old cell-sized
  rasters must use the `grid` tag or the CSV. Documented as a deliberate change.
- `X-RSAL-*` headers and new response fields are additive.
- Regenerating stale exports costs one inference on download; the previous
  behaviour (serving an old artifact) was silent data drift.
