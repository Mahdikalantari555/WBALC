## Context

`POST /predict` already returns `hard_map` (`[rows][cols]` of class indices) and
`probability_map` (`[class][rows][cols]` of floats) over a pixel region, and
writes both to GeoTIFF. That is the whole model-derived story today: no
uncertainty artifact, no UI, and two contracts that only break at the edges —
the exported colormap does not match the UI palette, and the export transform
assumes uniform cells while the grid clamps its last row/column.

What the analyst needs on screen:

- **Classification**: per-patch class, in the legend's colours, so "the model
  says cropland here" is verifiable at a glance.
- **Uncertainty**: per-patch disagreement, because that is the field the active
  learning query ranks by. Seeing it as a map turns "12 uncertain patches" into
  "an uncertain boundary between two fields".
- Both **toggleable**, independent of each other and of the label/suggestion
  layers, with their own opacity, and both **exportable** in a form that opens in
  QGIS (GeoTIFF) and in a form that drops into a report (PNG/CSV).

Constraints: maps are patch-grid resolution by design (one cell per patch —
`PATCH_SIZE=32`, stride = patch size by default); a 4000×4000 scene is 125×125
cells, so the payload is small in cell count but the class-probability tensor is
not (125×125×classes floats); training is synchronous, so inference must not
block the event loop; and the frontend must not gain a second coordinate system.

## Goals / Non-Goals

**Goals**
- Two new toggleable layers, painted from the exact grid the backend exported.
- Uncertainty defined identically to the query ranking it explains.
- Every layer exportable as GeoTIFF, PNG and CSV.
- On-screen classes and exported classes use the same colours.
- Exported rasters align with the source scene cell-for-cell.
- Maps that are older than the latest training run are visibly stale.

**Non-Goals**
- No per-pixel (sub-patch) inference — the grid resolution is deliberate.
- No server-rendered tiles / no new tiling infrastructure.
- No new uncertainty estimators beyond the three the AL service already defines.
- No model or training changes, no DB migration.
- Not building multi-region (viewport-scoped) inference; maps are full-dataset.

## Decisions

### D0. Uncertainty is derived in the browser (product-owner decision)
The classification layer is a single class index per cell and already exists on
the wire. Uncertainty is **derived client-side** from the per-class probabilities
returned by `POST /predict` (`include_maps: true`), reusing the same maths as
`al_service.uncertainty_scores` (entropy / margin / least-confidence), so no
second source of truth is introduced for what is shown on screen.

Consequences, accepted deliberately:
- the browser needs the probability tensor once per `(dataset, iteration)`, so
  the adapter caches that response and the layer panel's method switch is a pure
  client recomputation (no request);
- **the export must still be produced server-side**, because a GeoTIFF has to
  carry the grid/CRS and must be reproducible outside the browser. The exported
  uncertainty is computed by the backend from its own probabilities; a
  cross-check test asserts the two implementations agree to 1e-6 on a fixture,
  which is what keeps "client truth" and "export truth" from drifting.

D1 below therefore describes the *optional* compact endpoint kept for large
scenes; it is no longer on the critical path for showing the layer.

**As built (divergence from the decision above).** The field endpoint did land on
the critical path, because `POST /predict` returns the full probability tensor
(classes × rows × cols, float32) and shipping that to the browser just to paint
one scalar field is wasteful on real scenes; the export was server-side anyway.
So the single source of truth for the maths moved to
`inference_service.uncertainty_scores` and **both** consumers now read from it:

- `GET /predict/map` computes the field once, server-side, and serves the scalar
  `values` grid the map paints (`persist=False`, so a read never writes an
  export row);
- the PNG/CSV/GeoTIFF exporters call the same function, so what is exported is
  bit-identical to what is displayed, with no cross-implementation tolerance to
  police;
- `POST /predict` still carries `uncertainty_map` / `valid_map` for the batch
  workflow, also from that function.

Read-only paths (`/predict/map`, `.png`, `.csv`, `/legend`) never persist a
GeoTIFF; only `/download/{type}` does. Listing endpoints collapse to the newest
artifact per `(dataset, type, method)` so repeated reads cannot inflate history.

### D1. One scalar field endpoint (for large scenes)
`GET /projects/{id}/predict/map?dataset_id=&layer=hard|uncertainty&method=&iteration=`
returns:

```json
{
  "layer": "uncertainty", "method": "entropy",
  "dataset_id": 3, "model_iteration": 7, "training_run_id": 12,
  "grid": { "rows": 125, "cols": 125, "patch_size": 32, "stride": 32,
            "region": {"x0":0,"y0":0,"x1":4000,"y1":4000} },
  "classes": ["water","vegetation"],
  "values": [[0.11, 0.72, ...], ...],
  "min": 0.0, "max": 1.0,
  "stale": false
}
```

`values` is a compact 2-D array (rows × cols) — class indices for `hard`,
normalised uncertainty in `[0,1]` for `uncertainty`. It exists so a scene whose
probability tensor is too large to ship to the browser can still show both
layers; the default path is D0.

`values` for `uncertainty` is computed by `al_service.uncertainty_scores`, i.e.
byte-identical maths to the query ranking it explains. A test asserts that the
patches of an uncertainty batch are the top cells of the same run's field —
otherwise the layer and the query could silently disagree.

### D2. Uncertainty maths lives in one place
`al_service.uncertainty_scores` (already entropy/margin/least-confidence,
higher = more uncertain, normalised) is reused verbatim by the map endpoint. The
alternative — a second implementation in `inference_service` — would let the map
disagree with the ranking that selected the batch, which is the one property
this feature exists to make visible. Method defaults to `entropy`; `least_confidence`
and `margin` are selectable in the layer panel and are part of the cache key.

### D2b. Colour has exactly one definition per layer (as built)
The palette already had a drift test; the uncertainty ramp did not, and the
first build shipped *two* ramps — a three-stop cool→warm ramp on screen and a
hard-coded blue→red formula in the PNG exporter — so the exported picture did
not match the map. Both sides now read the same three stops
(`#3c78c8 → #f0e6a8 → #e0663c`) and a test asserts the frontend array equals
`inference_service.UNCERTAINTY_RAMP`, mirroring the class-palette guard.

The ramp is also **relative to the field's own `[min, max]`**, not to absolute
0..1. A trained model's entropy on an easy scene sits in a narrow band (here
0.68–1.00), so an absolute ramp painted the entire map one shade of orange and
communicated nothing. Stretching to the field's range makes structure visible;
the legend prints both endpoints and says the colour is stretched, so the
numbers remain the contract.

### D3. Classes are painted from the UI palette, everywhere
The backend's private `_palette()` is replaced by a single exported
`CLASS_PALETTE` (hex) used for: the GeoTIFF colormap, the PNG export, and
(documented, duplicated deliberately) `frontend/src/lib/palette.ts::CLASS_COLORS`.
A test asserts the two lists are identical, so the on-screen class colours and
the exported colours cannot drift again.

### D4. Export geometry matches the grid exactly
`grid_transform` currently assumes `cell_w = cell_h = min(stride, patch)` for
every cell, but `make_grid` clamps the last row/column to the image edge, so the
clamped cells are drawn at the wrong place in the exported raster. Two options
were considered: (a) emit a per-cell transform — impossible in a single GeoTIFF
affine; (b) **emit the raster on a uniform `stride` lattice covering the region,
writing nodata (65535) in the cells the map does not cover**, and keep the true
patch windows in a sidecar `grid` tag. (b) is exact, keeps the export a plain
affine GeoTIFF, and matches "pixel = cell (row, col)" so a QGIS user and the map
agree. The map draws cell rectangles from the same per-cell windows, so edge
cells are visibly the clamped size they really are.

### D5. Layers are canvas tiles built once, cached per key
The map builds the layer as an offscreen canvas of `rows × cols` pixels (one
pixel per cell) and hands it to a Leaflet `ImageOverlay` with
`image-rendering: pixelated`, sized by the **same** `pixelToDisplay` transform
used for markers (from `fix-sample-map-alignment`). Cache key:
`(projectId, datasetId, layer, method, trainingRunId)`. Rendering cost is
`rows × cols` fills once; pan/zoom cost is the browser compositing one image,
which is why this is the performance choice over per-cell polygons or per-tile
fetches. Uncertainty uses a two-stop ramp (low = cool, high = warm) with a
continuous legend and a numeric readout on hover; classification uses
`CLASS_PALETTE` with the existing class legend, extended so clicking a class
toggles its visibility in the layer.

Nodata cells: patches whose window is entirely nodata/invalid produce
all-zero features (`patch_features` → `nan_to_num`) and still get a confident
prediction. The map endpoint returns a `valid` mask (per-cell boolean) and both
layers render invalid cells transparent; the CSV and PNG export mark them
`nodata`. This prevents painted grass over the black collar of a rotated scene.

### D6. Exports are one call each, from one menu
- `GET /download/hard` — existing, colormap fixed (D3), transform fixed (D4).
- `GET /download/uncertainty?method=` — new float32 GeoTIFF, one band, plus a
  `method` tag and the grid tag.
- `GET /download/probability` — existing, unchanged.
- `GET /projects/{id}/exports/{...}.png` and `.csv` — rendered/serialised on the
  server from the same field, so a PNG always equals the GeoTIFF content.
- UI: an "Export" section inside the layers panel (what you see) and a
  "Maps" section in analytics (what you have), both listing exports with
  dataset, layer, iteration and staleness. Download is a plain link to the BFF
  route so the browser handles the file; no JS buffering.

### D7. Staleness is derived, not stored
`stale` is computed by comparing the map's `training_run_id` with the project's
latest run at request time. The layer keeps rendering the old map but the panel
and legend show "from iteration N · retrain available". Confidence in the
displayed field should never be higher than confidence in its freshness.

## Risks / Trade-offs

- **Grid-resolution maps look blocky.** Accepted: it is the model's actual
  resolution; smoothing would imply sub-patch knowledge. Pixelated rendering and
  a "1 cell = 32 px" caption make it honest.
- **Uncertainty without probabilities in JSON** means the UI cannot re-derive
  uncertainty client-side without a second call. Accepted; the layer panel's
  method switch triggers one request, cached.
- **Full-dataset inference per (layer, method, iteration)** is synchronous and
  can take seconds on large scenes. Mitigation: inference runs in the worker
  thread (already the pattern), the endpoint is cached per key, and the UI shows
  a progress state with the ability to keep reviewing. A future async job queue
  would replace the request/response shape without changing the payload.
- **Nodata validity** flips cells that currently produce invented predictions.
  Existing tests that assert a full hard map will need the mask to default to
  all-valid for synthetic fixtures — deliberate, since "all valid" is the
  correct answer for a fixture with no nodata.
- **Two payload shapes** (`/predict` with maps, `/predict/map`) is mild
  duplication. Accepted for backwards compatibility with `scripts/demo.py` and
  the existing test suite; `/predict` is positioned as the scripted/GeoJSON
  path and `/predict/map` as the UI path.
- **PNG/CSV server rendering** adds Pillow-free code (rasterio can write PNG via
  its own driver) — must not pull a new dependency into the lock file.

## Migration Plan

1. Backend: shared `CLASS_PALETTE`, grid-correct export (D4), uncertainty export
   type, `valid` mask; tests for each. Existing tests stay green (mask defaults
   valid).
2. Backend: `/predict/map` endpoint with caching keying and staleness.
3. Adapter: BFF route for the map payload and for each export; no browser
   access to `/download/*` directly (it stays server-side, like every other
   RSAL call).
4. Frontend: layer canvas builder + Leaflet overlay; layer panel controls
   (toggle, opacity, method); legends; staleness badge.
5. Frontend: export menu (layers panel) and analytics "Maps" section.
6. Verify: pytest, typecheck, build, live smoke that toggles both layers,
   exercises each export, re-opens the GeoTIFFs with rasterio, and compares a
   rendered PNG against the on-screen layer.

## Open Questions

- Should the classification layer default **on** after the first successful
  training run, or stay off until the analyst asks? Default: off, with a one-time
  hint — a map that appears unrequested is easy to mistake for the imagery.
- Should uncertainty support a **threshold filter** (show only cells above
  `u ≥ τ`) as well as a continuous ramp? Default: ramp plus a slider in a
  follow-up, since the query already has a batch size to bound the work.
