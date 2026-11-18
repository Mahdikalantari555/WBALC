# Verification — wire-geospatial-research-frontend

Executed 2026-11-18 on branch `arena/8cc2470d-wbalc` (base `6d74b5b`).
Scope: the SvelteKit example only. **No backend code changed** —
`git status app tests frontend` is clean for this change.

## What was rebuilt

`examples/wbalc-geospatial-research-interface/` was a static demo (React bridge,
bundled illustration, `src/lib/data/research.ts` mock arrays, English only). It is
now a SvelteKit 5 application:

- `src/lib/server/rsal.ts` + `src/lib/server/adapter.ts` + `src/routes/api/**`:
  server-side BFF to RSAL using `$env/dynamic/private`. 14 route handlers
  (health, projects, project, datasets, dataset file, scenes, labels CRUD, label
  import, query, runs, map-field, exports).
- `src/lib/types.ts`: view models carrying provenance (run iteration, resolution,
  protocol, dataset, validity).
- `src/lib/geo.ts`: shared affine/projection maths with WGS84, Web Mercator and
  UTM (326xx/327xx/269xx) support; unsupported CRS falls back to pixel space with
  a reason instead of a wrong position.
- `src/lib/raster.ts`: client-side GeoTIFF rendering via HTTP Range on the
  adapter's file route (LRU handle cache, sampled 2–98% stretch).
- `src/lib/i18n/` + `src/hooks.server.ts` + `src/lib/components/LocaleSwitch.svelte`:
  typed `en`/`fa` dictionaries, cookie-seeded SSR `<html lang dir>`, runtime
  switch, `Intl` formatting, logical-property RTL CSS.
- Six views on live data; the browser-local review queue is keyed per project.

All mock modules, the bundled `public/maps/` illustration, the React bridge and
`vite-plugin-singlefile` were deleted. `npm run check:i18n` guards the
dictionaries; `npm test` covers geometry, adapter shaping, i18n and components.

## Commands and results

| Command | Result |
| --- | --- |
| `npm run check` (svelte-check + tsc) | **0 errors, 0 warnings** |
| `npm test` (Vitest, 4 files) | **36 passed** (geo 11, adapter 9, i18n 12, jsdom components 4) |
| `npm run check:i18n` | **300 keys** complete in `en.ts` + `fa.ts`, placeholders match |
| `npm run build` (adapter-node) | succeeded, `build/` 3.6 MB |
| `node build` + `GET /api/health` | `{"adapter":true,"engine":true,"detail":"ok"}` |
| `scripts/research_frontend_smoke.py --base :5173` (dev) | **60 checks passed** |
| `scripts/research_frontend_smoke.py --base :5174` (prod build) | **60 checks passed** |
| `docker compose config` equivalent (YAML parse) | `research-workspace` service present under the `research` profile |

### End-to-end smoke coverage (60 assertions)

health · SSR `lang`/`dir` for both locales · Persian chrome in SSR HTML · project
list/get with taxonomy · dataset list with WGS84 bounds + adapter-relative URL ·
**byte-identical** raster proxy (74 182 B) · **Range forwarded** (206, 1 024 B) ·
`/predict/map` before training → 409 · uncertainty cold start → the engine's own
actionable 409 · diversity batch (20) · pixel windows + geo centres · 12 label
submissions · **label correction versions the same sample (v2, count unchanged)** ·
training · `/runs` with protocol, per-class metrics and an `insufficient` flag
that mirrors the engine string · hard + uncertainty map fields on the prediction
grid · GeoTIFF export on the source grid (256×256, CRS present) · post-training
uncertainty batch with scores · two scene registrations + scene metadata · WGS84
GeoJSON import (imported 1 / skipped 1) · **unknown class `reed` refused, not
recoded** · projected-CRS import honoured only when declared · label deletion
removes every version · nav labels differ between `en` and `fa`.

## Issues found and fixed during verification

1. The file route sent an empty `range:` header when the client had none, which
   RSAL rejected with a 500. Fixed by forwarding Range only when present.
2. `insufficient` was derived from any evaluation string starting with
   `insufficient`, so `insufficient_data`-style values were indistinguishable from
   a real score. Now only `insufficient_train*` (training-fit fallback) counts.
3. UTM rasters were reported as `unsupported-crs`, i.e. pixel space, which would
   have put real Sentinel scenes off the geographic map. Added the UTM inverse and
   verified numerically (500000/4649776 → 3.000000°E, 41.999998°N).
4. Label import assumed WGS84 with no way to say otherwise. Now the coordinate
   system is an explicit choice (`EPSG:4326` default, or the dataset CRS), and
   nothing is guessed.

## Residual limitations (documented in the example README)

- No per-date water-area series: the engine registers scenes but does not classify
  them yet, so the timeline plots acquisitions and says area change is unavailable.
- No auth/user model; review state is per browser.
- Uncertainty/hybrid batches require a patch-resolution checkpoint (engine rule,
  surfaced verbatim).
- Map rendering supports WGS84/Web Mercator/UTM only; other CRSs are drawn in
  pixel space with an explicit notice.
- The example is not a default compose service (`--profile research`).
