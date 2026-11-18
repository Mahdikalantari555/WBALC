# TerraLab — RSAL frontend

Human insight. Earth intelligence. A satellite active-learning workspace wired
**exclusively** to the RSAL FastAPI backend — every query, label, training run,
and metric is real. There is no demo mode and no frontend database.

## What you can do

- **Projects** — create projects with 2–12 land-cover classes; live stats
  (labels, patches, accuracy, F1, model version) come from the backend.
- **Datasets** — drag-and-drop GeoTIFF upload (≤100 MB), metadata inspector,
  2D/3D preview, download-free client-side band rendering (true color, false
  color/NIR, NDVI, custom RGB), dataset deletion (cascades labels + exports).
- **Active learning** — query batches with diversity (cold start), entropy,
  margin, least-confidence, or hybrid strategies; review on a Leaflet map
  (WGS84 basemap, or pixel-space view for scenes without a CRS) with real patch
  outlines and patch-accurate spectral previews.
- **Labeling** — keyboard-first review (`1–9` class, `Enter` accept, `S` skip,
  `←/→` navigate, `N` note, `P` point, `?` help), batch grid mode with
  accept-all, point/polygon/rectangle drawing, GeoJSON/CSV import with class
  mapping, label correction (versioned) and deletion.
- **Analytics** — learning curve from real training history, class
  distribution, confusion matrix, per-class precision/recall/F1/support,
  CSV + JSON export.

## Architecture

```
Browser ── /api/* (Next.js route handlers = BFF adapter) ── RSAL_API_URL ──► FastAPI
```

- `src/lib/server/` — the adapter: translates browser shapes to the RSAL
  contract, reprojects coordinates with proj4 (UTM/NAD83/WGS84), fans out
  project stats, proxies raster bytes, and passes backend errors through
  with actionable messages. `RSAL_API_TOKEN` never reaches the browser.
- `src/stores/review-queue.ts` — RSAL queries are stateless, so the current
  batch persists in the browser (zustand + localStorage) and is reconciled
  with saved labels from `GET /labels`.
- `src/lib/geotiff.ts` — renders band combinations in-browser from the
  original GeoTIFF (2–98% stretch, ≤1200 px). Reads use HTTP Range requests, so
  opening a scene costs a few KB and a review thumbnail costs a windowed read of
  exactly that patch's pixels (`renderPatch`), not a scaled copy of the scene.
  One parsed handle + stretch per dataset (LRU, 3).
- `src/lib/geo.ts` — the single pixel↔display transform, shared verbatim by the
  BFF adapter and the browser. Thumbnails, markers, patch footprints, the warped
  raster overlay and submitted labels all go through it, so a pixel has one
  meaning everywhere. It also mirrors the backend patch grid
  (`gridAxis`/`cellWindow`, including the clamped last row/column).
- Georeferencing: a north-up UTM scene is drawn on the WGS84 basemap with its
  basemap tiles; rotated or sheared scenes are **warped** onto the basemap with
  the same corner fit that places the markers (a plain north-up image overlay
  would put the imagery up to a few patches away from the labels). Scenes whose
  reprojection is not affine (no CRS, unsupported CRS, or a fit residual >2% of
  the scene span) fall back to a pixel-space map (Leaflet `CRS.Simple`, no
  basemap) with the reason stated in the map attribution; labels are then stored
  in pixel coordinates.
- Map layers are scoped to the active dataset: samples and drafts belonging to
  another scene are never drawn on top of the current one.
- A saved label reloads exactly where its query sample was drawn: the pin is the
  patch *centre* (not the clicked point or the patch origin), and the footprint
  is recovered from the stored geometry in whichever space RSAL kept it
  (`map` = projected CRS, or `pixel`). `patchWindowForLabel` in `lib/geo.ts` is
  the one implementation, unit-tested for both spaces.

### Model layers

Once a project has a checkpoint, the map can show what the model thinks about
the scene on screen:

- **Classification** — one flat colour per cell, from the shared class palette
  (`lib/palette.ts`, identical to the backend's `CLASS_PALETTE`). The layer panel
  states whether the field is *pixel-level* (one prediction per source pixel) or
  *patch cells* (one value per patch, block-filled), together with the cell size,
  so a cell map is never read as per-pixel inference. Individual classes can be
  hidden, which is how you check one class at a time.
- **Uncertainty** — the scalar field from `al_service.uncertainty_scores`
  (`entropy`, `margin` or `least_confidence`), painted on a cool→warm ramp.
  The ramp is stretched over the field's own min/max because a trained model's
  entropy rarely spans 0..1; the legend prints both endpoints and says so.

Both layers default **off**, persist across reloads, have independent opacity
sliders, and paint as a single `ImageOverlay` per field (`image-rendering:
pixelated`, one canvas pixel per cell) so panning and zooming cost nothing. If a
newer training run exists than the one that produced the field, the panel says
so instead of silently showing stale colours; if the model's band count does not
match the dataset, the layers are hidden with an explanation.

`src/lib/layers.ts` holds the vocabulary shared by the server routes and the
browser (`MAP_LAYERS`, `UNCERTAINTY_METHODS`, `isUncertaintyMethod`);
`src/lib/overlay.ts` holds the painting (`fieldToDataUrl`, `uncertaintyColor`,
`UNCERTAINTY_RAMP`). `src/lib/server/map-routes.ts` is the BFF side, wrapped by
the thin `app/api/projects/[id]/map/**` route handlers.

Exports download the field you are looking at: GeoTIFF (with colormap, `grid`
and `method` tags), PNG (the same picture, invalid cells transparent) or CSV
(one row per cell with class, probability, uncertainty and pixel windows). The
layers panel links them per layer; the analytics view has a **Maps** card
listing every export with its iteration and staleness. Submitting labels or
training invalidates the cached fields, so a visible layer switches to the new
model's output immediately instead of showing the previous run's colours.

## Run locally

Start the backend first (repo root):

```bash
.venv/bin/uvicorn app.main:app --port 8000
```

Then:

```bash
cd frontend
npm install
cp .env.example .env.local        # optional; defaults to http://localhost:8000
npm run dev                       # http://localhost:3000
npm test                          # geo, overlay and adapter-payload tests (node:test)
npm run typecheck && npm run lint
```

Production: `npm run build && npm start`. Quality gates: `npm run typecheck`,
`npm run lint`.

| Variable | Default | Purpose |
|---|---|---|
| `RSAL_API_URL` | `http://localhost:8000` | Backend base URL (server-side only) |
| `RSAL_API_TOKEN` | — | Optional bearer token, kept server-side |

## Docker

From the repo root: `docker compose up -d --build` starts the API on `:8000`
and this frontend on `:3000` (`RSAL_API_URL=http://api:8000`). The image is a
multi-stage build running the Next.js standalone server as a non-root user.
`npm ci` uses long fetch timeouts/retries and a BuildKit cache mount; on a slow
or restricted network set `NPM_REGISTRY` in the root `.env` (or
`--build-arg NPM_REGISTRY=...`) to build through a mirror. The lockfile already
includes the Alpine/musl native binaries, so no extra system packages are needed.

## End-to-end smoke test

With both services running (repo root):

```bash
.venv/bin/python scripts/frontend_smoke.py --base http://localhost:3000
```

Creates a project, uploads a synthetic GeoTIFF, and exercises the whole loop
through the browser-facing API: cold-start diversity query → labels → train →
metrics → model-based queries → corrections → polygon labels → import →
deletes → cleanup.
