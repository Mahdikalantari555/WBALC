# WBALC performance audit

Audit date: 2026-11-18 · Branch `arena/8cc2470d-wbalc` (base `6d74b5b`)
Scope: the FastAPI engine (`app/`), the SvelteKit research workspace
(`examples/wbalc-geospatial-research-interface/`), and the Next.js TerraLab
workspace (`frontend/`), plus the container/CI packaging.

Measurement method: `scripts/audit_performance.py` (new) drives live HTTP with
`httpx`, 5 repetitions per path, reporting p50/p95/min in milliseconds. It runs
against a real engine (`uvicorn`, SQLite, local storage) and the **production**
adapter-node build, not a dev server. Fixtures are synthetic GeoTIFFs
(4-band uint16, DEFLATE, 10 m pixels, EPSG:32631) at 1024² and 2048². All
numbers below are from this machine; treat absolute values as relative
indicators, not SLAs.

---

## 1. Verdict

The project is **fast enough for its intended single-researcher use and has no
pathological slow endpoints**. Everything a reader touches in the UI answers in
single-digit milliseconds of overhead except the three operations that
legitimately compute: query selection, training and inference.

Two real problems were found and **fixed in this audit**:

1. **The workspace shipped every view's code on first paint.** Leaflet (146 KB)
   and the GeoTIFF reader (49 KB) were in the initial graph for a user who only
   wanted the overview. Fixed with per-view dynamic imports: **initial JS 315 →
   180 KB raw, 108 → 67 KB gzip (−43%)**, and Leaflet/GeoTIFF are now fetched
   only when the map or learning view opens.
2. **Map-field requests re-inferred on every toggle.** Each `/predict/map` call
   is a full inference on the engine (~230–700 ms depending on grid). The
   workspace now memoizes one field per dataset+layer+method+run, so toggling
   layers back and forth costs nothing after the first fetch.

Four smaller findings are documented below with recommendations but **not**
changed, because each would require backend work or a scope decision that
belongs to its own OpenSpec change.

---

## 2. Measured latency (p50 / p95 / min, ms)

Adapter = SvelteKit `+server.ts` BFF on the production build. Engine = direct.

| Path | via adapter | direct to engine | adapter overhead |
| --- | ---: | ---: | ---: |
| `GET /health` | 2.9 / 6.2 / 2.7 | 1.2 / 1.6 / 1.1 | +1.7 |
| `GET projects` | 4.0 / 4.1 / 3.7 | 1.9 / 2.3 / 1.7 | +2.0 |
| `GET datasets` | 5.9 / 14.1 / 4.9 | 3.2 / 3.4 / 3.0 | +2.7 |
| `GET labels` | 6.1 / 6.8 / 6.0 | 2.7 / 2.8 / 2.3 | +3.4 |
| `GET runs` (`metrics/history`) | 4.1 / 4.3 / 4.0 | 2.4 / 2.7 / 2.3 | +1.7 |
| `GET dataset file` (6.8 MB GeoTIFF) | 34.4 / 49.5 / 29.8 | — | — |
| `GET dataset file` (64 KB Range) | 4.8 / 12.9 / 3.9 | — | — |
| `POST query` diversity (1024 patches, 20) | 153.6 / 159.8 / 148.4 | — | — |
| `POST train` patch (12 labels) | 826.8 (single run) | — | — |
| `GET map-field` hard (32×32 cells) | 277.8 / 288.4 / 231.5 | — | — |
| `GET export` hard GeoTIFF | 175.6 / 342.3 / 8.9 | — | — |
| `GET /` (SSR shell) | 3.6 / 4.8 / 3.3 | — | — |

**Scaling check on a 2048² scene** (27.3 MB, 4096 patch cells, same engine):

| Operation | Time |
| --- | --- |
| `POST query` diversity (4096 candidates) | 620 ms |
| `POST train` patch (20 labels) | 1223 ms |
| `GET map-field` cold | 696 ms |
| `GET map-field` immediately again | 732 ms (engine recomputes; the UI cache now prevents this) |
| `GET export` hard (1.21 MB GeoTIFF) | 1083 ms cold / **17 ms warm** |
| `GET dataset file` (27.3 MB) | 122 ms |

Interpretation:

- **Adapter overhead is 1.7–3.4 ms**, i.e. 1.5–2× the engine's own latency but
  absolutely negligible. Most of it is a second JSON parse/serialize plus
  Node's fetch, which is expected for a BFF. `/labels` is the largest because it
  also fetches the dataset list to attach `dataset`/`center` metadata — two
  upstream calls, still 6 ms total.
- **Query selection scales sub-linearly**: 4× the candidates cost 4× the time
  (154 → 620 ms), i.e. linear in patch count with a 0.15 ms per-candidate cost.
  That is the diversity/uncertainty feature extraction, not the API.
- **Exports are cached by the engine once produced** (1083 ms → 17 ms), and the
  generator invalidates on a newer run. Good design; the cold path is the only
  cost.
- **The engine does not cache `/predict/map`.** Each call re-runs inference. For
  map use that is the dominant cost, and it is the reason the frontend cache in
  §1 item 2 matters.

---

## 3. Frontend payload and rendering

| Metric | Before | After | Change |
| --- | ---: | ---: | --- |
| Initial JS (entry + route node, raw) | 315 KB | **180 KB** | −43% |
| Initial JS (gzip) | 108 KB | **67 KB** | −38% |
| Leaflet in initial graph | yes (146 KB) | **no** | lazy |
| GeoTIFF reader in initial graph | yes (49 KB) | **no** | lazy |
| Per-view chunks | — | Geospatial 28 KB, Learning 23 KB, Evaluation 10 KB, Arena 9 KB | on demand |
| CSS | 51.6 KB / 11.5 KB gzip (single bundle) | unchanged | — |
| Fonts | 48 KB Inter woff2 + 15 KB Plex Mono woff2, self-hosted | unchanged | — |
| SSR shell TTFB | — | 3.6 ms p50 | — |

Notes:

- The remaining 99 KB chunk is the two i18n dictionaries (both locales inline)
  plus shared UI. Keeping both languages in the bundle is deliberate: a locale
  switch must not require a round trip, and 99 KB gzip-compressed is ~30 KB.
  If that ever matters, the locale dictionaries are the first candidate for a
  dynamic import.
- Bounds are recomputed in WGS84 server-side (UTM inverse), so the map never
  needs a projection library in the browser. `proj4` is deliberately absent.
- Rasters use HTTP Range: opening a 27 MB scene fetches only the header and the
  tiles covering the view, and a review thumbnail reads a single 32 px window.
  The adapter forwards Range verbatim (only when present — forwarding an empty
  `range:` header made the engine 500, fixed earlier).
- Canvas previews are capped at 1400 px per side, and the stretch is sampled
  from five spread windows instead of a full low-res read, so preview cost does
  not grow with scene size.

---

## 4. Backend hot paths

| Area | Observation | Assessment |
| --- | --- | --- |
| Patch features (`raster_service`) | per-patch `mean/std/min/max` per band, computed from windowed reads | fine for hundreds–thousands of patches; 0.15 ms/patch measured |
| Pixel mode (`inference_service`) | loops 256×256 windows, but accumulates a full `K×H×W` probability cube plus a full validity mask in memory | **documented limit**, guarded by `max_raster_elements`; not out-of-core (this is exactly the gap `harden-pixel-classification-contract` 4.2 tracks) |
| Training (`pipeline`/`training_service`) | fits RF/LightGBM on extracted features; ~0.8 s for 12 labels, 1.2 s for 20 on a 4096-cell grid | dominated by feature extraction, not the model |
| Inference / map fields | re-runs the model over the whole raster on each request; no result cache | the single biggest avoidable cost for interactive use; mitigated client-side |
| Exports | written atomically, then verified by reopening; served from disk afterwards | good: cold cost once, warm 17 ms |
| Label listing | latest-version query per sample | 2.7 ms direct; no N+1 observed |
| Scene listing | single select per project | 3 ms direct |
| Database | SQLite via aiosqlite, WAL not configured explicitly | fine at this scale; see §5 |
| Storage | local immutable files, `STORAGE_DIR` | fine; no copies of source rasters |

What scales badly, in order:

1. **Full-scene inference per request** (map fields, each export type). Linear
   in raster area and re-done on demand.
2. **Pixel-mode memory** (full probability cube). Bounded by a config sanity
   limit, not by streaming.
3. **Feature extraction re-run per query** on very large grids (0.15 ms/cell ⇒
   4096 cells ≈ 0.6 s; a 10 000² scene would be ~25 s).
4. **SQLite write contention** if multiple users ever train concurrently.

None of these affect the current single-user workflow at the tested sizes.

---

## 5. Recommendations (not implemented here)

| # | Finding | Recommendation | Effort | Needs backend? |
| --- | --- | --- | --- | --- |
| P1 | `/predict/map` re-infers per request (~0.3–0.7 s) | Cache the field per (run, dataset, method) on the engine, invalidated by run id — the UI cache is a mitigation, not a fix | M | yes |
| P2 | Map field payload is dense rows of numbers (32×32 = 1 K cells today; a 10 000² scene is 97 656 cells ≈ 1 MB JSON) | Serve a compact representation (base64/quantized or a small GeoTIFF/PNG reused for the canvas) once grids grow past ~256×256 | M | yes |
| P3 | i18n dictionaries ship both locales in the initial bundle (~99 KB chunk) | Split per locale with a dynamic import when the bundle budget matters | S | no (frontend) |
| P4 | `frontend/` (Next.js) still imports its whole workspace eagerly | Same per-view `dynamic()` treatment used here; measure with `next build` output first | S | no (frontend) |
| P5 | No HTTP compression asserted on the adapter | The adapter-node build emits `.br`/`.gz` assets; verify the deployment fronts them with compression (the compose service has no reverse proxy) | S | no (deploy) |
| P6 | SQLite without explicit WAL/pragma tuning | Enable WAL and a busy timeout if concurrent use is expected | S | yes |
| P7 | No profiling harness in CI | `scripts/audit_performance.py` can gate a coarse budget (e.g. p95 < 50 ms for list endpoints) | M | no |

---

## 6. Reproduction

```bash
# engine
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# production build of the workspace
cd examples/wbalc-geospatial-research-interface
npm ci && npm run build
RSAL_API_URL=http://localhost:8000 PORT=5174 node build

# measurements (creates and deletes its own project)
cd /home/user/WBALC
.venv/bin/python scripts/audit_performance.py --base http://localhost:5174

# correctness still holds after the changes
.venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5174   # 63 checks
cd examples/wbalc-geospatial-research-interface && npm run check && npm test && npm run check:i18n
```

## 7. Changes made under this audit

- `src/lib/Workspace.svelte`: per-view dynamic imports with a component cache and
  a load-error state (only the overview stays in the initial graph).
- `src/lib/state.svelte.ts`: bounded LRU cache for map fields keyed by
  dataset+layer+method+trainrun, plus an early return when everything requested
  is already known; failed fetches are never cached.
- `scripts/audit_performance.py`: the measurement harness used for every number
  in this report.

Verified after the changes: `svelte-check` 0/0, 40 unit + component tests pass,
`check:i18n` 325 keys, adapter-node build succeeds, and the live smoke passes
all 63 checks against the production build.
