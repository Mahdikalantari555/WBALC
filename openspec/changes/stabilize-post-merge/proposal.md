## Why

The pixel/geospatial stabilization PR merged pixel-resolution classification and
tightened parts of the raster path, but a post-merge audit (see `audit.md`)
reproduced correctness defects that were not covered by the merged tests:

1. Patch-mode GeoTIFFs are written on a stride lattice that cannot represent the
   clamped edge cells, so on non-divisible scene sizes the last row/column is
   georeferenced in the wrong place (up to one stride of displacement) and the
   export extends past the source extent.
2. Class probabilities are returned for cells the same response marks invalid,
   so probability and uncertainty outputs carry different masks.
3. Active-learning queries break (HTTP 500) after a pixel-resolution run and can
   suggest patches with no valid pixels at all; the SOM explorer does the same and
   also clusters nodata patches.
4. Checkpoints are loaded with an unvalidated `joblib.load`, so an incomplete or
   incompatible checkpoint surfaces as HTTP 500 instead of an actionable error.
5. The API does not report which resolution produced a map, or the evaluation
   parameters behind a metric set, so a patch-cell map can be read as a
   pixel-level map.
6. Documentation and the license inventory make claims that no longer match the
   code (test counts, lattice padding, evaluation labels, dependency paths).
7. 29 npm advisories (10 moderate / 19 high) are still open, two of which are
   fixable without major upgrades.

The goal is a verified stabilization of the existing application — no new
research features, no WBALC work, no public-API removals.

## What Changes

- **Exports are exact.** Patch-mode hard/probability/uncertainty GeoTIFFs are
  written on the source grid by replicating each cell's value over its true pixel
  window (nearest-neighbour block fill, no interpolation); pixels outside any cell
  are nodata. Pixel mode keeps its one-value-per-pixel path. Every export is
  written to a temporary file, atomically renamed, reopened and compared to the
  expected source window (dimensions, CRS, affine, bounds) before an `Export` row
  is created. Exports gain `resolution` and `nodata` tags.
- **One validity mask everywhere.** `maps_from_inference` masks probabilities as
  well as hard/uncertainty values; `POST /predict` returns `null` probabilities for
  invalid cells; probability exports always declare nodata.
- **Active learning rejects incompatible models explicitly.** `/query` and the SOM
  explorer use a checkpoint only when it was trained at patch resolution with a
  matching band count; otherwise they return a 409 (query) or run without model
  annotations and say so (SOM explorer). Candidates are restricted to patches
  with valid pixels; the SOM explorer fits on valid patches only and reports
  `valid_patches`/`nodata_patches`.
- **SOM pixel mode uses strict all-band validity**, matching supervised pixel mode.
- **Checkpoints are validated on load** (`format`, required keys, `model.classes_`
  vs stored classes, `bands`, `resolution`), with an actionable 409 instead of a
  500, and a `feature_schema`/`n_features` record so a patch checkpoint can never
  be silently used as a pixel checkpoint or vice versa.
- **The API reports resolution and evaluation context**: `predict`, `predict/map`,
  `train` and `metrics` include `resolution`; metrics include
  `evaluation_strategy`, `n_train`, `n_test`, `held_out_groups` and
  `per_class_iou`.
- **Downloads never serve a stale artifact silently**: `GET /download/{type}`
  regenerates when the newest export predates the latest run and exposes
  `X-RSAL-Model-Iteration` / `X-RSAL-Stale` headers.
- **Frontend**: the adapter forwards `resolution`/`evaluation_strategy`/`params`
  to `/train` and sends `sample_resolution` for pixel-mode labels; the map states
  whether the painted field is pixel- or patch-resolution.
- **Docs and licensing**: README and AUDIT are corrected (test counts, export
  semantics, evaluation labels, resolution modes, NoData rules, limitations);
  `THIRD_PARTY_LICENSES.md` records dependency paths and the full LGPL surface;
  fixable npm advisories are upgraded and the rest are documented.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `raster-grid`: exports must reproduce the source grid exactly, including
  clamped edge cells; validity masks must be consistent across hard, probability
  and uncertainty outputs.
- `pixel-classification`: pixel-mode exports keep one value per source pixel;
  patch-mode exports are block-filled cells on the same grid and are labelled as
  such.
- `inference-export`: resolution is reported; exports are validated after write;
  downloads do not return stale artifacts without saying so.
- `model-training`: checkpoints record and validate their feature schema,
  resolution and class order.
- `evaluation`: metrics expose their strategy and sample counts, including the
  in-sample fallback.
- `active-learning-query`: queries are restricted to valid patches and to
  models whose feature schema matches the query grid.
- `som`: the SOM explorer/classifier ignore invalid observations and reject or
  ignore incompatible checkpoints explicitly.
- `frontend-workspace`: the map states the classification resolution and the
  adapter forwards the resolution/evaluation options it displays.

## Impact

- Backend: `app/services/{inference_service,training_service,raster_service}.py`,
  `app/services/pipeline.py`, `app/services/som_service.py`, `app/api/{query,som,
  inference,training}.py`, `app/schemas.py`.
- Frontend: `frontend/src/lib/server/handler.ts`, `frontend/src/lib/server/map-routes.ts`,
  `frontend/src/types/index.ts`, `frontend/src/components/map/map-viewer.tsx`,
  `frontend/src/lib/server/handler.test.ts`.
- Tests: new `tests/test_post_merge_stabilization.py` plus additions to existing
  API suites; frontend adapter unit test.
- Docs: `README.md`, `AUDIT.md`, `THIRD_PARTY_LICENSES.md`,
  `openspec/changes/stabilize-post-merge/*`.
- Dependencies: `postcss` and the `typescript-eslint` chain (non-major only).
- No API removals. New response fields are additive; `/query` gains an explicit
  409 for pixel-resolution checkpoints where it previously returned 500.
- Patch-mode GeoTIFF dimensions change from "one pixel per cell" to the source
  region size — a deliberate correctness change documented in the README and the
  `grid`/`resolution` tags.
