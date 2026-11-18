## Context

The workspace shows the same sample in two places: a thumbnail in the review
panel and a marker on a Leaflet map. Both are supposed to describe one patch of
one GeoTIFF. Today each is computed independently:

| Where | Source of position | Coordinate maths |
|---|---|---|
| Review thumbnail | whole raster rendered to a 1200 px PNG data URL | CSS `background-position` percentage under a fixed `background-size: 600%` |
| Map marker | `QuerySample.coords.center_x/y` (pixel) | `proj4`, per point |
| Map overlay | dataset bbox corners | 4-corner reprojection, axis-aligned fit |
| Map patch rectangle | `sample.bbox` (selected sample only) | `proj4`, per corner |
| Submitted label | display-space geometry | reverse `proj4` |

Five paths, three different notions of "where", and one of them (CSS) is not
even linear. The reported symptom is the predictable result.

Constraints that matter here: rasters are north-up UTM (EPSG:326xx/327xx) up to
roughly 10 km on a side; scenes without a usable CRS must still work in pixel
space; the backend's patch grid clamps the final row/column to the image edge
(`app/services/raster_service.py::make_grid`), so cell size is not uniform; and
the browser must stay responsive while panning a 4000×4000 scene.

## Goals / Non-Goals

**Goals**
- One pixel→display transform, used everywhere a sample is drawn or submitted.
- Thumbnails that are literally the patch pixels the model saw.
- Deterministic dataset↔sample scoping: no cross-scene markers.
- A visible, honest failure mode when georeferencing cannot be trusted.
- Cheaper thumbnails (windowed read) than today (full-image render per sample).

**Non-Goals**
- No change to the RSAL API, patch grid, or model features.
- No re-rendering of raster bands for the map (that stays client-side as today).
- No classification/uncertainty map layers — those are the follow-up change
  `add-map-overlay-layers`.
- No basemap alignment work for rotated/polar scenes beyond the warning and
  pixel-space fallback.
- No new dependencies.

## Decisions

### D1. Patch pixels come from a windowed GeoTIFF read, not CSS
`getPatchThumbnail(dataset, window)` opens the dataset once (cached `GeoTiff`
handle), reads `readRasters({ window: [x0, y0, x1, y1], width: 96, height: 96,
interleave: true })`, applies the same percentile stretch as the main image and
returns a PNG data URL rendered with `image-rendering: pixelated`. The window is
the **exact** pixel window from `coords.x0/y0/x1/y1` (already returned by
`/query`), so what the analyst sees is what the model classified. No CSS
position maths exists in the thumbnail path any more.

Stretch: percentile range computed per patch is flat for homogeneous water, so
the stretch window is computed **per dataset** (cached alongside the parsed
handle) rather than per patch. Cached per `(datasetId, bandMode)`.

### D2. One shared transform module, browser and server
New `frontend/src/lib/geo.ts` exporting pure functions with no Node
dependencies — `applyAffine`, `invertAffine`, `projectionDef`, `toWgs84`,
`fromWgs84`, `pixelToDisplay`, `displayToPixel`, `patchWindow`, `cellRect`.
`frontend/src/lib/server/geo.ts` is rewritten as a thin re-export of these plus
the RSAL-shaped wrappers it already has, so adapter and browser cannot drift.
`displayToPixel` is new and is what label submission uses; today submission
duplicates the forward maths with its own `convertPair`.

### D3. Footprints for every sample, from the real grid
Each sample carries `pixel` (top-left `x0/y0`) and `bbox` (display rectangle of
its patch) computed from the query's `coords`, so the grid's clamped edge cells
are honoured — no client-side `col * stride` reconstruction. The map draws the
footprint for the selected sample always and for others on hover; the thumbnail
draws the same rectangle implicitly by being the crop. Saved labels (from
`/labels`) get `pixel` and `bbox` too by inverting the dataset transform, so a
corrected label and its thumbnail agree after a reload.

When a sample has no `pixel` (map-coordinate point label far from any patch
centre, imported geometry), the thumbnail falls back to a centred window of one
patch around the converted pixel and the map draws only the geometry — the UI
says "no patch footprint" in that case rather than inventing one.

### D4. Dataset scoping is a filter, not a hope
`LeafletMap` receives the active dataset and renders samples/drafts whose
`datasetId` matches (or that have no `datasetId` and only the project has one
dataset). Drafts created by drawing record the active dataset id at creation
time — `MapViewer.onDraw` already passes `dataset?.id`, so this is a type and
filter change, not new plumbing. The review panel always uses
`sample.datasetId`, never the currently selected dataset.

### D5. Warped overlay + honest georeferencing check
The north-up `ImageOverlay` is replaced by a **warped** overlay: a
least-squares affine fit maps source pixels to normalised display coordinates
through the four reprojected corners, and the raster is painted through that fit
into a canvas that Leaflet stretches over the dataset's display bbox. Markers are
placed with per-point reprojection, which agrees with the fit to well under a
pixel: measured 1.4e-6° (~0.15 m) at 256 px and 3.5e-4° (~38 m) at 4000 px for a
36.9° rotated scene, i.e. <0.1 % of the scene span.

`assessGeoreferencing(ctx)` therefore reports `mode: 'map' | 'pixel'`, the fit,
and the reason:
- no transform → `not-georeferenced`;
- CRS not resolvable by `projectionDef` → `unsupported-crs`;
- corner-fit residual above 2 % of the scene span → `non-axis-aligned`
  (reprojection is not affine over this extent, so no single image quad is
  honest).

The good news from measurement: every realistic north-up UTM scene *and* rotated
scenes up to ~40 km stay on the basemap. Only genuinely non-affine cases
(unsupported CRS, very large or polar extents) drop to pixel space, where the
image and the samples are guaranteed consistent; the map attribution then states
the reason so "the imagery is warped" is never mistaken for "the labels are
wrong". `tilt` is reported for the affected axis so the UI can note that the grid
is not north-aligned.

### D6. Thumbnail context toggle is a zoom, not a different code path
The "context" affordance grows the *window* by one patch on each side and reads
that (still windowed) instead of a different rendering mode. Same code path, so
the default stays verifiable.

### D7. Performance
- One parsed `GeoTiff` per dataset, opened through `fromUrl` (HTTP Range) and
  cached in a module-level LRU (cap 3); today every thumbnail mount fetched and
  re-rendered the whole raster.
- The BFF forwards `Range` (backend `FileResponse` already answers 206), so a
  thumbnail costs a windowed read of ~a few KB of blocks instead of the whole
  file. Verified: 12 range requests of 11–60 ms for a full review panel warm-up.
- The stretch is sampled from five spread windows per dataset (not a full
  low-resolution read, which would still pull every block) and cached per band.
- One shared handle also serves the map's full-scene PNG, so switching band modes
  no longer re-downloads the scene.
- Footprints are pure maths on already-fetched sample data; no new requests.
- The warped overlay is one canvas → one data URL per dataset+band mode, so
  pan/zoom cost is a single composited image (a 1600 px-wide canvas).

## Risks / Trade-offs

- **Percentile stretch per dataset** can wash out a patch that is uniformly
  brighter or darker than the scene. Accepted: a per-patch stretch would make
  two adjacent patches look unrelated, which is a worse failure for review.
- **Pixel-space fallback is less useful for real review** (no basemap context).
  Accepted and made explicit in the UI; the alternative is silently wrong
  coordinates.
- **Caching parsed TIFFs** raises memory with many datasets. Mitigation: LRU cap
  of 3 datasets, dropped on dataset switch/delete.
- **`ImageOverlay` corner fit** remains approximate for very large scenes even
  when the axis-alignment check passes. Documented; the tolerance is measured on
  the corners the fit uses, so a scene that is genuinely badly warped trips the
  fallback.
- Labels stored before this change have no `pixel`; they are re-derived from
  geometry on read, so no migration is needed and history stays intact.

## Migration Plan

1. Land `lib/geo.ts` + `server/geo.ts` re-export and the type additions
   (`pixel`, `bbox` always present, `datasetId` required for map rendering)
   with the old code paths still working.
2. Switch the adapter to emit `pixel`/`bbox` for saved labels.
3. Replace `SamplePatch` with the windowed crop; keep the old CSS class for
   layout only.
4. Filter map layers by dataset, add hovering footprints and the georeferencing
   badge.
5. Verify: typecheck, production build, live smoke against a running backend
   (`scripts/frontend_smoke.py`), and a side-by-side manual check that the
   thumbnail border matches the map footprint at the scene's four corners and
   centre.

## Open Questions

- Should the thumbnail show the patch outline explicitly (a 1 px border) or is
  the crop edge enough? Default: crop edge only, border on hover.
- Should footprints be drawn for all pending samples by default, or only on
  hover? Default: hover, plus always for the selected sample — avoids a 100×100
  grid of rectangles at low zoom.
