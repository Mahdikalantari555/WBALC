# WBALC research workspace (SvelteKit)

The primary WBALC frontend, with English and Persian (RTL). Observations, labels,
metrics, predictions, and rasters come from the live FastAPI engine through a
server-side adapter. The root launchers serve this workspace on port 3000.

## Runs against WBALC (RSAL)

```sh
# 1. Start the engine (repo root)
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Start this app
cd frontend
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
| `BODY_SIZE_LIMIT` | `545259520` in Docker/native launcher | Multipart envelope limit in bytes. Set this when running `node build` directly (adapter-node otherwise defaults to 512 KiB). |
| `ORIGIN` | `http://localhost:3000` in Docker/native launcher | Set to the public frontend URL for production behind a reverse proxy. |

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

## Workspace views

| View | Reads from the engine |
| --- | --- |
| Project & data | Create a study, upload a GeoTIFF for training, or register a dated scene |
| Overview | projects, datasets, scenes, labels, training runs → readiness checklist, acquisition timeline, latest metrics |
| Geospatial Workspace | original GeoTIFF bytes (`/dataset/{id}/file`), `/predict/map` hard + uncertainty fields, labels |
| Temporal Analysis | `/scenes` metadata and native-grid comparison (no implicit alignment) |
| Active Learning | Durable query batches, labeling and GeoJSON import, model training, JSON research path and CSV sample ledger |
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
- **Durable rounds.** Query batches and submitted decisions are stored in the
  engine. Drafts are browser-local. The research-path export includes all
  persisted rounds, even those outside the recent-history display.
- **Bilingual with no i18n dependency.** `src/lib/i18n/` holds typed `en`/`fa`
  dictionaries and a locale store; `src/hooks.server.ts` stamps `<html lang dir>`
  from the `wbalc.locale` cookie so the first paint is already correct, and a
  runtime switch updates strings, direction and `Intl` formatting without a
  reload. Layout uses logical (`ms-`, `me-`, `ps-`, `pe-`, `text-start`) CSS.
## Scope and limitations

- Single-workspace, no authentication; the adapter forwards an optional token but
  the app has no user model.
- Unsaved review state is per browser.
- The engine's own limits still apply: uncertainty/hybrid queries need a
  patch-resolution checkpoint, and identical band counts are not proof of
  compatible spectral schemas.
- No imagery is bundled. On an empty engine, use **Project & data** to create your first project.
