## 1. Shared transform module
- [x] 1.1 Extract browser-safe `frontend/src/lib/geo.ts`: affine helpers, projection defs, CRS↔WGS84, `pixelToDisplay`, `displayToPixel`, `gridAxis`/`cellWindow`/`pointToCell`, `assessGeoreferencing`, `overlayTransform`
- [x] 1.2 Rewrite `frontend/src/lib/server/geo.ts` as a re-export + RSAL wrappers; adapter behaviour unchanged
- [x] 1.3 Route label submission through `displayToPixel` (drop the duplicated `convertPair`)
- [x] 1.4 Unit tests (`npm test`, node:test): affine/app round trips, grid clamp parity, edge cells, corner-fit accuracy, pixel-space fallbacks — 14 passing

## 2. Patch-accurate thumbnails
- [x] 2.1 Cached `GeoTiff` handle (`fromUrl`, range reads) + sampled per-dataset stretch in `lib/geotiff.ts`; LRU cap 3, dropped on dataset delete
- [x] 2.2 `renderPatch(url, datasetId, window, bandMode)`: windowed `readRasters` → pixelated PNG data URL
- [x] 2.3 Replace `SamplePatch` background-image maths with the crop; keep layout class, drop the fixed `background-size: 600%` and percentage positioning; crosshair is now the patch edge
- [x] 2.4 Use the sample's own dataset (never the map's selection), with the dataset name in the caption
- [x] 2.5 Centred one-patch fallback + explicit "no patch footprint" copy for samples without a window
- [x] 2.6 Optional context toggle: grow the window by one patch, same read path
- [x] 2.7 BFF forwards `Range` so thumbnails read blocks instead of whole files

## 3. Footprints and dataset scoping on the map
- [x] 3.1 Adapter: query samples and saved labels both carry `window`, `pixel` and patch `bbox`, derived from geometry + transform
- [x] 3.2 `Sample` type: `window`/`pixel`/`bbox` always resolved or explicitly absent; drafts store their dataset id
- [x] 3.3 `LeafletMap`: filter samples and drafts by the active dataset
- [x] 3.4 Draw the selected sample's footprint always, hovered samples' footprints on hover
- [x] 3.5 Keep the crosshair "locate sample" behaviour consistent with the footprint bounds

## 4. Georeferencing honesty
- [x] 4.1 `assessGeoreferencing` with a corner-fit residual predicate (2 % of span) + `tilt`
- [x] 4.2 Map switches to pixel space with a stated reason for `not-georeferenced` / `unsupported-crs` / `non-axis-aligned`
- [x] 4.3 Attribute line reports the active presentation and the reason
- [x] 4.4 Warped raster overlay: imagery painted through the same corner fit as the markers (`overlayTransform`)
- [x] 4.5 Verified against live fixtures: north-up UTM on the basemap (tilt 0.015°), 36.9° rotated scene warped (corner error 2e-6°)

## 5. Verification
- [x] 5.1 `npm run typecheck && npm run lint && npm run build && npm test` green
- [x] 5.2 Checked thumbnail vs map footprint at grid corners and centre (north-up UTM) against live backend data; pixel-space path unit-tested
- [x] 5.3 Live smoke: upload → query → label → reload; `/labels` returns windows whose pixel windows match the query contract
- [x] 5.4 Updated `frontend/README.md` with the transform module, range-read thumbnail path and georeferencing rules
- [x] 5.5 Saved-label reload parity: a submitted label reloads as the same
      `window`/`polygon`/display pin as the query sample it came from. Fixed two
      defects found by the adapter smoke: `map`-space labels were inverted as if
      they were WGS84 (wrong patch, up to half a patch away), and point pins were
      re-drawn at the clicked/patch-origin point instead of the patch centre the
      query sample is drawn at. `npm test` 21 passing (3 new); adapter smoke now
      69/69 (the `pixel label round-trips display` check had been failing).
- [~] 5.6 Reviewer sign-off on visual alignment (live preview). Automated
      alignment is covered end-to-end; a human look at a representative scene is
      still the last word, and browsers cannot be driven in this sandbox.
