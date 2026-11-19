## Why

The backend already produces a hard classification map and per-class probability
maps (`POST /projects/{id}/predict`, `inference_service.maps_from_probabilities`)
and exports them as GeoTIFFs (`GET /download/hard|probability`), but the
TerraLab workspace shows none of it. The analyst reviews 32 px patches as dots on
imagery with no view of what the model thinks the rest of the scene is, and the
only way to obtain either map is a hand-written `curl`.

Two gaps:

1. **No map view.** The layers panel has "model suggestions / labeled samples /
   opacity" and nothing model-derived. Classification and uncertainty are the
   two views an active-learning analyst needs most: where the model disagrees
   with itself, and where it is confident, is the field the next query samples.
2. **No uncertainty artifact.** Uncertainty exists only transiently inside
   `/query` (`al_service.uncertainty_scores`) as a ranking score per candidate
   patch. There is no uncertainty map, no export, and no way to compare the
   ranking the query used against the map the analyst sees.

## What Changes

- Add a **classification layer** to the map: per-patch class from the model,
  painted with the same class colours the legend uses.
- Add an **uncertainty layer**: per-patch entropy / margin / least-confidence,
  from one light endpoint that returns only the scalar field the map needs.
- Both layers are **toggleable** in the existing map layers panel, with their
  own opacity, and both are scoped to the active dataset and training run.
- Add **exports**: classification GeoTIFF (already exists), uncertainty GeoTIFF
  (new), plus PNG snapshots of exactly what is on screen and a CSV of the
  per-patch table. All exports are reachable from the map and the analytics view.
- Backend additions (additive, no contract break):
  `GET /projects/{id}/predict/map?dataset_id&layer=hard|uncertainty&method&iteration`
  returning the grid-aligned field with its grid metadata, and
  `GET /projects/{id}/download/{type}` extended with `uncertainty`.
- Fix the **colour contract**: the exported colormap currently comes from a
  private backend palette while the UI uses `CLASS_COLORS`, so exported classes
  and on-screen classes are different colours. The export colormap becomes the
  same deterministic palette as the UI.
- Fix the **grid geometry contract** in exports: `grid_transform` assumes a
  uniform cell size while `make_grid` clamps the last row/column, so edge cells
  are misplaced in exported GeoTIFFs. Exports get a per-cell-correct transform
  (or an explicit nodata pad), matching what the map draws.
- Mark maps **stale** when a newer training run exists than the one that produced
  them, instead of silently showing an old model's output.

## Capabilities

### New Capabilities
- `map-overlays`: toggleable classification and uncertainty map layers in the
  workspace, with legend, opacity, staleness state and dataset/iteration scope.

### Modified Capabilities
- `inference-export`: uncertainty export type, uncertainty map endpoint, shared
  colour palette, grid-correct export transform.
- `frontend-workspace`: the map layers panel gains model-derived layers and
  their controls.

## Impact

- Backend: `app/api/inference.py`, `app/services/inference_service.py`,
  `app/schemas.py`, `app/services/al_service.py` (shared uncertainty maths),
  and new tests.
- Frontend: `lib/server/handler.ts` (map + download routes), `lib/api.ts`,
  `hooks/use-projects.ts`, `components/map/map-viewer.tsx`,
  `components/map/leaflet-map.tsx`, `components/analytics.tsx`,
  `app/globals.css`, `lib/palette.ts`.
- Rendering uses a canvas-tiled `ImageOverlay` built from the map endpoint
  payload (one request per dataset/iteration/layer, cached), so panning and
  zooming cost nothing extra and no full-image float payload is needed.
- Depends on `fix-sample-map-alignment` for the shared pixel↔display transform;
  layers are drawn with that transform and must not reintroduce a second one.
- No database migration: exports already have `type`, `region`,
  `training_run_id`; `uncertainty` is a new value of `type`.
