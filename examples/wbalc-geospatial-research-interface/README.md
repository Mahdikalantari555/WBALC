# WBALC research workspace (SvelteKit example)

A second, research-oriented frontend for the WBALC engine. It is **not** a
mock: every observation, label, metric, prediction and raster byte on screen is
fetched from the live WBALC (RSAL) FastAPI backend through a thin server-side
adapter. The Next.js TerraLab workspace in `frontend/` remains the primary UI;
this example exists to exercise the same backend contracts from a different
stack (SvelteKit 5 / Svelte 5 runes / Vite / Leaflet) and to offer a bilingual
(Persian/English, RTL) interface.

## Runs against WBALC (RSAL)

```sh
# 1. Start the engine (repo root)
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Start this app
cd examples/wbalc-geospatial-research-interface
npm ci
RSAL_API_URL=http://localhost:8000 npm run dev
```

Open the URL Vite prints (default <http://localhost:5173>). The engine URL is read
**on the server only**; the browser never talks to RSAL, so there is no CORS
surface and no backend URL in the client bundle.

### Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `RSAL_API_URL` | `http://localhost:8000` | Base URL of the WBALC engine (server-side). |
| `RSAL_API_TOKEN` | unset | Optional bearer token sent as `authorization` on adapter requests. |
| `PORT` | `5173` | Port the dev/preview/Node server binds to. |
| `HOST` | `0.0.0.0` | Bind address for the production Node server. |

Copy [`.env.example`](.env.example) to `.env` for local development.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with HMR (`0.0.0.0:5173`). |
| `npm run build` | Production build (`adapter-node`, output in `build/`). |
| `npm start` | Serve the production build (`node build`). |
| `npm run check` | `svelte-check` + TypeScript diagnostics. |
| `npm test` | Vitest: geometry, adapter shaping, i18n and jsdom component tests. |
| `npm run check:i18n` | Fails if the `en`/`fa` dictionaries diverge or placeholders differ. |

## The six views

| View | Reads from the engine |
| --- | --- |
| Overview | projects, datasets, scenes, labels, training runs → readiness checklist, acquisition timeline, latest metrics |
| Geospatial Workspace | original GeoTIFF bytes (`/dataset/{id}/file`), `/predict/map` hard + uncertainty fields, labels |
| Temporal Analysis | `/scenes` metadata and native-grid comparison (no implicit alignment) |
| Active Learning | `/query` batches, label submit/delete, GeoJSON import |
| Model Arena | `/metrics/history` runs, confusion matrix, per-class metrics |
| Results & Evaluation | recorded protocol, per-class IoU, label distribution, CSV/JSON export |

## Design notes

- **Adapter (BFF).** `src/routes/api/**` proxies RSAL with `$env/dynamic/private`
  and translates engine payloads into the view models in `src/lib/types.ts`
  (`src/lib/server/adapter.ts`). Values RSAL does not provide stay `null`; the UI
  renders an empty state rather than a fabricated number.
- **Rasters are read, never rewritten.** `src/lib/raster.ts` opens the original
  GeoTIFF with geotiff.js using HTTP Range requests (forwarded by the adapter)
  and paints the requested band mode on a canvas. No reprojection, resampling or
  caching of derived pixels on the server.
- **Two coordinate systems, never mixed.** A dataset is drawn on a WGS84 overlay
  when it has a usable CRS (EPSG:4326, EPSG:3857, or a WGS84/NAD83 UTM zone) and
  a north-up affine; otherwise the map switches to pixel space (`CRS.Simple`) and
  says so. Unsupported CRSs are reported, not guessed (`src/lib/geo.ts`).
- **The queue is browser state.** RSAL `/query` is stateless, so the pending batch,
  drafts and skips live in `localStorage` per project, while submitted labels are
  written to the engine. Deleting a sample removes every version in RSAL.
- **Bilingual with no i18n dependency.** `src/lib/i18n/` holds typed `en`/`fa`
  dictionaries and a locale store; `src/hooks.server.ts` stamps `<html lang dir>`
  from the `wbalc.locale` cookie so the first paint is already correct, and a
  runtime switch updates strings, direction and `Intl` formatting without a
  reload. Layout uses logical (`ms-`, `me-`, `ps-`, `pe-`, `text-start`) CSS.
- **Honest boundaries.** The engine registers scenes but does not classify them or
  compute per-date water area yet, so the timeline plots *registered
  acquisitions*, and the temporal view states that area change is unavailable
  instead of inventing series values.

## Scope and limitations

- Single-workspace, no authentication; the adapter forwards an optional token but
  the app has no user model.
- Review state is per browser. There is no shared queue or server-side draft.
- The engine's own limits still apply: uncertainty/hybrid queries need a
  patch-resolution checkpoint, and identical band counts are not proof of
  compatible spectral schemas.
- No imagery is bundled. Without a project in the engine the app shows a
  connection/empty state and creates nothing.
