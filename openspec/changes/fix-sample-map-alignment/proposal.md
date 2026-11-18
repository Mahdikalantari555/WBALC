## Why

The sample thumbnail in the review panel and the same sample on the map do not
show the same ground. Reported as "the small showup of samples are different
from points that are zoomed in the map". Three independent causes were found in
the current frontend, none of them a rendering fluke:

1. **The thumbnail is not a patch.** `SamplePatch` paints the *whole image* as a
   CSS background at a fixed `background-size: 600%` and positions it with a
   percentage `background-position`. A patch is 32 px of a scene that may be
   4000 px wide (0.8 %), so the thumbnail shows roughly an order of magnitude
   more area than the sample. The 40×36 px crosshair box is decorative: it does
   not correspond to the patch footprint at any zoom level.
2. **Percentage background positioning is not linear.** Under
   `background-size: 600%`, `background-position: f%` centres the crop on image
   fraction `(100f + 10) / 120` instead of `f`. At the scene edge the crop is
   off by ~6.7 % of the image width (~4 patches on a 2000 px raster), and
   correct only at the centre — exactly the "it matches in the middle, not at
   the edges" behaviour.
3. **The thumbnail and the marker can belong to different datasets.**
   `SamplePatch` is handed `datasets.find(selectedDatasetId) ?? datasets[0]`
   and ignores `sample.datasetId`, while `LeafletMap` draws *every* sample in
   the project regardless of which dataset the overlay is showing. In a
   multi-scene project, markers from scene B are painted over scene A at
   coordinates from a different CRS and extent.

Two latent issues make the same class of bug likely to return:

- Only the selected sample draws its real patch `bbox`; every other point is a
  dot with no footprint, so there is nothing to compare the thumbnail against.
- The raster `ImageOverlay` is a north-up rectangle fitted to the reprojected
  image corners, whereas markers are placed with exact per-point reprojection.
  Harmless for the common north-up UTM scene, but silently wrong for rotated
  transforms or large scenes whose reprojected corners are not axis-aligned.

## What Changes

- Replace the CSS-background thumbnail with an **exact patch crop** read from
  the source GeoTIFF (`readRasters({ window })`) for the sample's own dataset
  and pixel window; render it as a pixelated `<img>`, never position maths.
- Introduce one shared **pixel ↔ display transform** module used by thumbnails,
  markers, footprints, the map overlay and label submission, so a pixel has a
  single definition of where it lives everywhere.
- Give every sample a **display-space footprint** (`bbox`) derived from the same
  patch grid the backend used (including the clamped last row/column), and draw
  it on the map for the selected sample and on hover.
- **Filter map layers by dataset**: only samples whose `datasetId` matches the
  dataset shown on the map are drawn; drafts inherit the dataset they were
  drawn on.
- Replace the north-up image overlay with a **warped overlay** painted through
  the same four-corner affine fit that positions markers, so imagery and samples
  agree for rotated/sheared scenes too instead of only for north-up ones.
- Add a **georeferencing honesty check**: scenes whose reprojection is not affine
  (no CRS, unsupported CRS, or a fit residual above 2 % of the scene span) switch
  to the pixel-space presentation with the reason stated in the map.
- Serve raster bytes with **HTTP Range** support (BFF forwards `Range`) and cache
  one parsed GeoTIFF per dataset, so a review thumbnail costs a windowed read of
  its patch rather than a full-scene download and re-render per sample.
- Optional "context" toggle on the thumbnail (patch only vs patch with one
  patch of surroundings) so the crop is verifiable against the map.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `frontend-workspace`: sample thumbnails and map markers must agree on a single
  pixel→display transform and a single dataset; every sample carries a
  footprint; a mismatch must be detectable rather than silent.

## Impact

- `frontend/src/lib/geo.ts` (new shared transform; `server/geo.ts` now re-exports
  it), `frontend/src/lib/geotiff.ts`, `frontend/src/lib/use-raster.ts`,
  `frontend/src/lib/geo.test.ts` (new, `npm test`), `frontend/tsconfig.json`
  (`allowImportingTsExtensions` for node:test imports),
  `frontend/src/components/sample-review.tsx`,
  `frontend/src/components/map/leaflet-map.tsx`,
  `frontend/src/components/map/map-viewer.tsx`,
  `frontend/src/types/index.ts`, `frontend/src/app/globals.css`.
- Adapter: saved labels always expose `pixel` + patch `bbox` (currently only
  point labels in pixel space do).
- No backend changes (FastAPI's `FileResponse` already honours `Range`), no API
  contract changes, no new dependencies.
- Existing keyboard shortcuts, label import and submission flows are unchanged.
