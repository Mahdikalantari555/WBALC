## 1. Backend contracts
- [x] 1.1 Shared `CLASS_PALETTE` in `inference_service`; replace private `_palette`; test that it matches `frontend/src/lib/palette.ts` CLASS_COLORS
- [x] 1.2 Grid-correct export transform: uniform stride lattice + nodata padding for clamped edge cells, `grid` tag with true patch windows
- [x] 1.3 Per-cell `valid` mask from nodata detection in `patch_features`/`load_raster`; invalid cells → nodata in exports
- [x] 1.4 `GET /projects/{id}/predict/map` (layer=hard|uncertainty, method, iteration, dataset_id) returning `values`, `valid`, `grid`, `classes`, `min/max`, `training_run_id`, `stale`
- [x] 1.5 Reuse `al_service.uncertainty_scores` verbatim; test that batch ranking matches top uncertainty cells
- [x] 1.6 `GET /download/uncertainty?method=` (float32 GeoTIFF + `method`/`grid` tags); extend `EXPORT_TYPES`
- [x] 1.7 PNG + CSV render/serialise from the same field (exactly what the map shows)
- [x] 1.8 Tests: map endpoint shapes and 409s, export headers/tags, colormap equality, edge-cell geometry re-opened with rasterio
- [x] 1.9 Read-only paths compute with `persist=False`; `GET /exports` collapses to the newest artifact per `(dataset, type, method)` (found in verification: map/PNG/CSV reads were writing GeoTIFFs)

## 2. Data path
- [x] 2.1 Uncertainty maths has **one** definition, `inference_service.uncertainty_scores`, read by `/predict/map`, the exporters and `POST /predict` (see design §D0 as-built: the field endpoint replaced the browser-side derivation)
- [x] 2.2 `lib/layers.ts` (server-safe): `UNCERTAINTY_METHODS`, `UncertaintyMethod`, `MAP_LAYERS`, `isUncertaintyMethod`
- [x] 2.3 Export routes for hard / uncertainty / probability / png / csv, streamed through the BFF, never exposing RSAL directly
- [x] 2.4 React Query key `(projectId, datasetId, layer, method, iteration)`; method switch re-keys the query
- [x] 2.5 Parity guard: frontend and backend uncertainty ramps must be identical (test), replacing the planned 1e-6 maths cross-check — one implementation made it moot
- [x] 2.6 Export links carry `format` + `method` + `datasetId`; `probability` is GeoTIFF-only (422 for png/csv)

## 3. Layer rendering
- [x] 3.1 `lib/overlay.ts`: cell field → offscreen canvas (classification palette / uncertainty ramp, invalid transparent)
- [x] 3.2 Leaflet `ImageOverlay` positioned from the grid transform, `image-rendering: pixelated`, z-index 3 (classification) / 4 (uncertainty)
- [x] 3.3 Classification legend reuses class colours and supports per-class visibility; uncertainty legend is a ramp with min/max and method name
- [x] 3.4 Class chips and the uncertainty min/max readout act as the readout (per-cell hover deferred, see design Open Questions)
- [x] 3.5 Render order: imagery → classification → uncertainty → footprints → labels; independent opacity sliders

## 4. Controls and exports in the UI
- [x] 4.1 Map layers panel: classification toggle, uncertainty toggle, uncertainty method select, per-layer opacity, class filter
- [x] 4.2 Staleness badge comparing `model_iteration` with the current iteration, plus a re-run hint
- [x] 4.3 Export links in the layers panel (GeoTIFF / PNG / CSV) for the visible layer
- [x] 4.4 Analytics "Maps" card: list exports with dataset, layer, iteration, staleness, download links
- [x] 4.5 No-model messaging; layers hidden and a note shown when the model's band count does not match the dataset

## 5. Verification
- [x] 5.1 `pytest` green — 111 passed (was 82; `tests/test_map_layers_api.py` alone holds 29)
- [x] 5.2 `npx tsc --noEmit`, `npx eslint .` and `npx next build` green; `npm test` 18 passed
- [x] 5.3 Live smoke: train → toggle both layers → switch method → export all formats → reopen GeoTIFFs with rasterio and the PNGs with Pillow, compare against the served field
- [x] 5.4 Update root `README.md` (endpoints + palette/grid contract) and `frontend/README.md` (layers, exports)
