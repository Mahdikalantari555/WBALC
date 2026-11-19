# RSAL stabilization audit

This file tracks the audit trail. The current change is
[`openspec/changes/stabilize-post-merge/`](openspec/changes/stabilize-post-merge/):
its `audit.md` lists every reproduced defect (D1–D16), and its
`verification.md` records the executed commands, results and residual risk.

## Status of the previous (merged) stabilization

Still true, and covered by tests: pixel mode uses per-pixel spectral vectors with
exact row-major alignment and block-wise reads; strict all-band validity; direct
per-pixel prediction with no upsampling; pixel exports inherit the reference
window affine and are reopened and compared; patch validity scans every pixel;
GDAL band masks are honoured; pixel sample ids exist for point labels; spatial
group holdout, per-class IoU and an explicit insufficient-data response exist.

Corrections to the previous report:

- The claim that patch exports are a "documented clamped-edge lattice" hid a real
  georeferencing defect: the lattice cannot represent clamped cells, so edge
  cells were displaced by up to one stride and exports overhung the source
  extent. Patch exports are now painted on the source grid (D1).
- `total_patches`/hit counts in the SOM explorer silently included nodata patches
  (D5, D13).
- "139 Python tests" was accurate at the time of that report; the counts in
  `README.md` (82) were stale and are corrected to 158.

## What this change fixed (verified)

- Patch GeoTIFF exports: exact source-grid geometry, atomic writes, reopen
  validation, `grid`/`resolution` tags; stride gaps are nodata.
- One validity mask across hard/probability/uncertainty, in JSON and on disk.
- `/query`: 409 for pixel-resolution checkpoints with uncertainty/hybrid,
  explicit degraded mode for diversity/SOM, and no nodata patches in any batch.
- SOM explorer: valid patches only; incompatible checkpoints reported instead of
  HTTP 500; pixel-mode SOM uses strict all-band validity; SOM exports land on the
  source grid.
- Checkpoints: `rsal-checkpoint-v2` with feature schema/count and class-order
  validation; legacy v1 accepted only as patch; actionable 409s.
- API: `resolution` on predict/map/train/metrics; evaluation context in metrics;
  downloads never serve an artifact from a previous run without saying so.
- Frontend: adapter forwards training options and `sample_resolution`; the map
  states pixel vs patch cells.
- Docs and licensing: README/AUDIT corrected, third-party inventory rewritten
  with dependency paths and the actual LGPL surface; `postcss` upgraded.

## Verification executed (2026-11-18)

- Backend: `pytest` → **158 passed** (baseline before the change: 139 passed).
- Frontend: `npm test` → **25 passed**; `npm run typecheck` clean;
  `npm run lint` → 0 errors (7 pre-existing warnings); `npm run build` succeeded.
- `npm audit`: 29 advisories (10 moderate / 19 high) → 28 (10 / 18).
- `pip-audit -r requirements.lock.txt` and `-r requirements-dev.txt`: no known
  vulnerabilities.

## Still open / deliberately deferred

- `deck.gl` (loaders.gl/luma.gl/image-size) and `eslint-config-next`
  (fast-glob/picomatch/micromatch) advisories: only resolvable by semver-major or
  downgrade changes. Triage and reachability documented in
  `THIRD_PARTY_LICENSES.md`.
- Licensing review of LGPL `sharp`/libvips binaries, Esri terms, amCharts terms
  and Hippocratic-2.1 React-Leaflet.
- Streaming pixel inference and buffered (non-block-boundary) spatial validation.
- OGC polygon topology validation; label `sample_id` forgery hardening.
- Pixel-mode training is API-only; the workspace trains patch models.

## Performance audit (separate deliverable)

[`PERFORMANCE.md`](PERFORMANCE.md) is the dedicated performance audit: live
latency measurements for the engine and the SvelteKit adapter, bundle sizes, the
scaling behaviour on a 1024² and a 2048² scene, ranked bottlenecks and
recommendations. It is not a stabilization record — this file stays scoped to
correctness. Two findings from that audit were fixed in the workspace under this
change (per-view code splitting and map-field memoization).

## Raster intake and map follow-up (2026-11-19)

- Folder/manual band intake now skips `merged.tif` (and merged-name variants),
  normalizes Sentinel band aliases including NIR08, B11/SWIR16, B12/SWIR22 and
  SCL, and can read STAC-style or MTL-style JSON metadata for acquisition time,
  sensor/platform, processing/product details, orbit and band resolutions.
- Single-band imports with co-registered native resolutions use the finest
  source grid when CRS and footprint match and coarser grids are integer-aligned.
  Continuous bands (including SWIR) use bilinear resampling; SCL/QA use nearest.
  Source scale/offset are applied, the alignment is recorded on scenes, and
  shifted/cropped/non-nested grids, CRS changes, merged inputs and multiband
  inputs still fail with actionable validation errors. Reprojection is not
  silently performed.
- Project-area intake normalizes Polygon/MultiPolygon geometries, Features and
  polygon FeatureCollections. Collections are combined into one Polygon or
  MultiPolygon, with a declared GeoJSON CRS preserved (WGS84 assumed when absent).
  The API boundary also accepts Feature/FeatureCollection payloads.
- The geographic map now has OpenStreetMap as its only basemap, with required
  attribution. Pixel-space rasters remain on a plain canvas.
- A bounded GDAL PNG preview and exact-pixel probe are available as fallbacks
  when geotiff.js cannot decode/read a TIFF. The browser no longer downloads an
  entire large TIFF as an implicit fallback. Both dataset and scene routes are
  project-scoped and window/pixel bounds are validated.

### Follow-up verification and residuals

- `./.venv/bin/python -m pytest -q --disable-warnings`: **367 passed, 1 skipped**
  (368 tests collected).
- `frontend`: `npm test` **120 passed**; `npm run check` **0 errors / 0
  warnings**; `npm run check:i18n` **666 matching keys**; production build passed.
- Stack tests cover 10 m / 20 m SWIR alignment, scale/offset, nearest-neighbour
  SCL preservation, merged/multiband rejection and invalid-grid rejection.
  Preview tests cover bounded PNG dimensions, pixel-window reads, named-band
  probes, nodata/bounds errors and project isolation.
- The reported `Offset is outside the bounds of the DataView` has not been
  reproduced against the user's original TIFF (no sample was supplied). A
  generated tiled/deflate GeoTIFF with the stack output profile reads successfully
  through geotiff.js Range requests; the library's inclusive range-end
  construction remains a possible, unproven contributor. The server preview/probe paths prevent that decoder error from
  blocking map imagery or pixel inspection, but root-cause confirmation still
  requires the failing file or a minimal reproduction.
- The UI requests standard OSM tiles directly from `tile.openstreetmap.org`; the
  browser needs network access to that service. No alternate basemap is offered.
- Test tooling still emits non-failing deprecation notices for Vitest's
  `environmentMatchGlobs`, Starlette's `httpx` test client integration, and
  Rasterio's affine multiplication operator.
