# WBALC — Water-Body monitoring with Active Learning

WBALC is a research-oriented system for water-body monitoring from satellite
imagery. This repository starts from the linked RSAL implementation and keeps
its FastAPI + async SQLAlchemy backend, rasterio storage/inspection, and
**SvelteKit** research workspace. The new multi-temporal scene foundation is
specified in [the scene ingestion specification](openspec/specs/scene-ingestion/spec.md).

The WBALC scene collection registers independent Sentinel-1 and Sentinel-2
GeoTIFF acquisitions with native-grid and sensor metadata. Registration keeps
the source file unchanged: it does not download, reproject, resample, harmonize,
or align scenes. Inherited labels, training, inference, and Active Learning
features remain scoped to the existing single selected `Dataset`; they are not
a multi-scene processing pipeline.

Backend: FastAPI + async SQLAlchemy (SQLite by default, Postgres via env) +
rasterio + scikit-learn / LightGBM. Training is synchronous (inherited MVP);
heavy raster/ML work runs in a worker thread so the event loop stays responsive.

Frontend: the bilingual (English/Persian, RTL) SvelteKit research workspace in
[`frontend/`](frontend/).
The browser talks to the engine through a same-origin server adapter.

## Capabilities

| Capability | Endpoints |
|---|---|
| Study project management | `POST/GET /projects`, `GET/PUT/DELETE /projects/{id}`; study-area geometry/CRS and WBALC three-class/binary configuration |
| Multi-temporal scene ingestion | `POST/GET /projects/{id}/scenes`, `GET /projects/{id}/scenes/{sid}`, `GET .../{sid}/spatial`, `DELETE .../{sid}` |
| Legacy dataset ingestion | `POST /projects/{id}/upload` (GeoTIFF), `GET /projects/{id}/dataset`, `GET .../dataset/{did}/file`, `DELETE .../dataset/{did}` |
| Label management | `POST/GET /projects/{id}/labels`, `GET /projects/{id}/history`, `DELETE /projects/{id}/labels/{sample_id}` |
| Active learning query | `POST /projects/{id}/query` (uncertainty / diversity / hybrid / som) |
| Unsupervised SOM | `POST /projects/{id}/som/classify` (pixel/patch spectral clustering + GeoTIFF), `GET/POST /projects/{id}/som` |
| Model training | `POST /projects/{id}/train` (rf / lightgbm), `GET /projects/{id}/metrics` |
| Inference & export | `POST /projects/{id}/predict`, `GET /projects/{id}/download/{hard\|probability\|som}` |

Interactive API docs: **`/docs`** (Swagger UI) and **`/redoc`**.

## Quickstart (local)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The database and storage directories are created on startup under `STORAGE_DIR`
(default `./storage`). Configuration is via environment or `.env`
(see [`.env.example`](.env.example)).

## Quickstart

Pick one path. Both bring up the same services; only the launcher differs.

### Everything in Docker

```bash
./scripts/dev.sh up                 # engine :8000 + SvelteKit workspace :3000
./scripts/dev.sh up --postgres      # ... with Postgres instead of SQLite
./scripts/dev.sh up --all --build   # Postgres and a forced rebuild

./scripts/dev.sh ps                 # status + health per service
./scripts/dev.sh logs api           # follow one service
./scripts/dev.sh smoke              # run the smoke suites from the host
./scripts/dev.sh down               # stop (data volumes are kept)
./scripts/dev.sh down -v            # stop and delete the volumes
```

The script wraps `docker compose` and exists for the failure modes that a plain
`up -d` hides: no daemon, a port already taken by a stale dev server, or
`--postgres` without `DATABASE_URL` (which would silently leave the engine on
SQLite). It checks those first and says what to fix. `docker compose up -d
--build` still works if you prefer it — the profiles are the same:
`--profile postgres` is optional.

### Or natively, no Docker

```bash
./scripts/up.sh                    # engine :8000 + SvelteKit workspace :3000
./scripts/up.sh --dev              # uvicorn --reload + vite dev (HMR)
./scripts/up.sh status
./scripts/up.sh logs engine
./scripts/up.sh down
```

On Windows, use PowerShell from the repository root:

```powershell
.\scripts\up.ps1 up
.\scripts\up.ps1 status
.\scripts\up.ps1 logs frontend
.\scripts\up.ps1 down
```

The Windows launcher builds the same SvelteKit app in `frontend/` and starts
it at `http://localhost:3000`. Use `up --dev` for Vite, or set `FRONTEND_PORT`
before starting to change the port. If an older launcher left a process on the
port, run `down` first. By default the launcher uses `.venv\Scripts\python.exe`;
set `WBALC_PYTHON` to use an existing compatible Python interpreter instead.

This creates `.venv` if needed, waits for the engine's `/health` before starting
any UI, writes pid files under `.run/` and one log per service. Use it in
sandboxes without a Docker daemon, or when you want reload/HMR.

Requires Docker with BuildKit (Docker 23+ / Compose v2) for the container path.
The API image installs the fully pinned
[`requirements.lock.txt`](requirements.lock.txt) for reproducible builds and
includes `libgomp1` (needed by LightGBM — without it the container starts and
`/health` passes, then the first LightGBM fit dies). The API healthcheck
therefore also imports `lightgbm, sklearn, rasterio`, so a broken image fails at
`up` instead of at the first request. Every UI waits for
`condition: service_healthy`, not merely for the container to exist.

### Slow or restricted networks

If a build fails with pip errors like
`Could not find a version that satisfies the requirement numpy` /
`(from versions: none)`, or npm stalls, it is almost always a network timeout
fetching the package index — not a bad dependency. The images already use long
timeouts, automatic retries, and BuildKit cache mounts (so a re-run reuses
downloaded packages). If it still fails, build through a mirror by putting this
in a `.env` file next to `docker-compose.yml` (see [`.env.example`](.env.example)):

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple   # any PyPI mirror you trust
NPM_REGISTRY=https://registry.npmmirror.com              # any npm mirror you trust
```

then `docker compose up -d --build` again. To refresh the pinned API
dependencies after editing `requirements.txt`, regenerate the lock from a clean
resolve (`pip install --dry-run --ignore-installed --report r.json -r requirements.txt`,
then pin the reported `name==version` set into `requirements.lock.txt`).

## Multi-temporal scene foundation

A new project without explicit classification settings uses internal classes
`open_water`, `emergent_vegetation`, and `land`, plus a configurable binary
interpretation (`water_vs_non_water` or `open_water_vs_other`). The internal
three-class configuration remains present in either export interpretation.

```bash
curl -X POST localhost:8000/projects -H 'content-type: application/json' \
  -d '{"name":"River study","study_area_crs":"EPSG:4326"}'

curl -X POST localhost:8000/projects/1/scenes \
  -F 'file=@sentinel2_l2a.tif' -F 'sensor=Sentinel-2' \
  -F 'acquisition_datetime=2024-06-01T10:15:00Z' \
  -F 'platform=Sentinel-2A' -F 'product_level=L2A' \
  -F 'processing_baseline=05.10' -F 'native_band_resolutions={"B02":10,"B11":20}'

curl localhost:8000/projects/1/scenes
curl localhost:8000/projects/1/scenes/1/spatial
```

Sensor selection is required; acquisition and product metadata are optional.
The upload response includes each scene's own bands, data types, NoData/mask,
CRS, affine transform, spatial bounds, dimensions, resolution, and timestamps.
The collection permits duplicate/missing dates, irregular intervals, different
sensors, extents, dimensions, pixel sizes, and CRS values. Listing sorts dated
scenes newest-first and leaves undated scenes last. Compare grid metadata before
any future pixel-wise operation; no scene is assumed to be aligned.

The database migration runner applies versioned additive migrations at startup.
Migration 1 adds project study-area/classification fields and creates the scenes
table; 2 adds `datasets.band_schema`, 3 adds `projects.taxonomy`, 4 adds
`labels.submitted_class_name`, 5 adds `training_runs.trained_classes`, 6 adds
`query_batches`/`query_items` plus the label → query-item link, 7 adds the
lineage columns (`content_sha256`, `size_bytes`, `sha256`, `manifest`,
`checkpoint_sha256`, `experiment_id`) plus the `experiments` table, and 8 adds
`scene_analyses` and `fusion_runs`. All are additive, idempotent and preserve
existing RSAL rows. A `NULL` band schema
means "undeclared": band identity is never backfilled from filenames or a sensor
default, so legacy datasets keep requiring an explicit override to be used.

## The active learning loop

1. **Create a project** with its class list:
   ```bash
   curl -X POST localhost:8000/projects -H 'content-type: application/json' \
     -d '{"name": "Coastal LC", "classes": ["water", "vegetation"]}'
   ```
2. **Upload a GeoTIFF** (multi-band supported; CRS, transform, shape, bands, dtype extracted):
   ```bash
   curl -X POST localhost:8000/projects/1/upload -F 'file=@scene.tif'
   ```
3. **Cold start**: query a diversity batch (no model needed):
   ```bash
   curl -X POST localhost:8000/projects/1/query -H 'content-type: application/json' \
     -d '{"strategy": "diversity", "batch_size": 10}'
   ```
4. **Label** the returned patches (point or polygon, pixel or map coordinates).
   Re-submitting the same `sample_id` (or a point in the same patch) stores a
   corrected version; full history is kept at `GET /projects/1/history`:
   ```bash
   curl -X POST localhost:8000/projects/1/labels -H 'content-type: application/json' \
     -d '{"labels": [{"geometry": {"type": "Point", "coordinates": [4, 4]}, "class_name": "water", "iteration": 0}], "auto_train": true}'
   ```
   `auto_train` triggers training on the current labels immediately; alternatively
   call `POST /projects/1/train {"model_type": "rf"}` (or `"lightgbm"`).
5. **Query with the model**: `strategy: "uncertainty"` (methods: `least_confidence`,
   `margin`, `entropy`) or `"hybrid"` (uncertainty pool + core-set diversification).
   Already-labeled patches are excluded by default. Each sample carries patch
   coordinates, georeferenced coords, prediction, confidence, uncertainty and an
   optional embedding.
6. **Inspect metrics**: `GET /projects/1/metrics` → accuracy, F1 macro/weighted,
   confusion matrix, per-class precision/recall/F1/IoU/support, plus the context
   the score belongs to (`resolution`, `evaluation_strategy`, `n_train`,
   `n_test`, `held_out_groups`). Checkpoints are saved per iteration under
   `STORAGE_DIR/models/` with their feature schema.
7. **Predict & export**:
   ```bash
   curl -X POST localhost:8000/projects/1/predict -H 'content-type: application/json' \
     -d '{"region": {"x0": 0, "y0": 0, "x1": 512, "y1": 512}}'   # region optional
   curl -OJ localhost:8000/projects/1/download/hard
   curl -OJ localhost:8000/projects/1/download/probability
   curl -OJ 'localhost:8000/projects/1/download/uncertainty?method=entropy'
   ```
   Maps carry one value per patch cell, painted over each cell's true pixel
   window **on the source grid** (nearest-neighbour block fill, never
   interpolated), so the export has the region's exact width/height, CRS, affine
   and bounds — including the clamped last row/column. Pixels covered by no cell
   (`stride > patch_size`) are nodata. For patch maps the `grid` tag lists every
   cell's pixel window in absolute source pixels; for pixel maps it records
   `cells_are_pixels: true` instead (a per-pixel cell list would be pointless and
   enormous). `resolution` says `patch-cells` or `pixel`.
   Hard maps are uint16 GeoTIFFs (pixel = 0-based class index, nodata 65535,
   colormap + `classes`/`grid`/`method`/`resolution` tags); probability maps are
   float32 with one band per class (nodata -9999); uncertainty maps are float32
   scalars (nodata -9999). All carry the source CRS/transform and are reopened
   and compared with the source window before the export row is created.
   Datasets without a CRS are refused (422) rather than written with a made-up
   georeference; the JSON map layers and CSV still work for them.

   The same fields drive the map UI and the lighter exports:

   | Endpoint | Purpose |
   |---|---|
   | `GET /projects/{id}/predict/map?layer=hard\|uncertainty&method=&dataset_id=&iteration=` | One scalar field (`values`, `valid`, `grid`, `classes`, `colors`, `min`/`max`, `stale`) for painting the layer |
   | `GET /projects/{id}/exports/{hard\|uncertainty}.{png,csv}` | Rendered/row-wise export of exactly that field (`probability` is GeoTIFF-only) |
   | `GET /projects/{id}/exports` | Newest artifact per `(dataset, type, method)`, with `iteration`, `method`, `stale` |
   | `GET /legends/classes` | The palette, so a class has one colour everywhere |

   Reading a field, a PNG, a CSV or a legend never writes an export row; only
   `GET /download/{type}` persists a GeoTIFF. A download never hands back an
   artifact from an older run: if a newer training run exists it re-runs
   inference first, and every response states `X-RSAL-Model-Iteration` and
   `X-RSAL-Export-Stale`.

A full scripted walkthrough against a running server:

```bash
.venv/bin/python scripts/demo.py --base-url http://localhost:8000
```

## Frontend — SvelteKit research workspace

Open `http://localhost:3000` after either launcher. In **Project & data**, create
or select a study and upload a training GeoTIFF. Use **Active Learning** to sample,
annotate, and train. Upload independent dated scenes for **Temporal Analysis**.
The frontend renders source imagery without requiring an online basemap.

In **Active Learning → Query history → Export research path**, choose:

- **JSON**: project and raster/scene metadata, all durable sampling rounds, all retained label versions, and training metrics and manifests.
- **CSV**: one row per sampled item with batch counts, pixel position, available map coordinates and CRS, score, uncertainty, prediction, confidence, and decision.

The `samples_added` count is the number of retained first label versions linked to
that batch, not the number of suggestions or class corrections. Labels entered or
imported separately remain in the JSON label ledger. Hard-deleted labels cannot be
recovered. A round before model training can have null predictions or uncertainty.
The research-path export is not a backup of raster or model binaries; spatial
products remain downloadable in the map and temporal views.

For standalone frontend development (with the engine already running):

```bash
cd frontend
npm ci
RSAL_API_URL=http://localhost:8000 npm run dev   # Vite on :5173
```

See the [workspace README](frontend/README.md)
and [OpenSpec frontend contract](openspec/specs/primary-frontend/spec.md).

## Classification resolution and evaluation

Training remains patch-based by default for backward compatibility. To explicitly
train a pixel-feature RF/LightGBM checkpoint, pass `"resolution": "pixel"` to
`POST /projects/{id}/train`. Pixel models use the source pixel's band values,
labels rasterized to source pixel centers (points use their containing pixel).
When collecting multiple point labels within a legacy patch for pixel-mode
training, submit each with `sample_resolution: "pixel"` so they are stored as
distinct pixel identities; without it, a second point in the same patch is stored
as a *correction* of the first (patch identity), which is the documented versioning
behaviour but silently reduces the pixel-mode training set. The model then predicts
every source pixel directly; this is not an upsampled patch map. Their hard,
probability and uncertainty GeoTIFFs use the source pixel/window affine and the
region dimensions, and a pixel that is nodata in any band is nodata in the output.
Pixel mode remains subject to the synchronous whole-raster memory guard described
under *Resource bounds* below.

Every response that describes a map states its `resolution` (`pixel` or `patch`),
so a patch-cell map is never presented as pixel-level classification. Patch-mode
`/query` and the SOM explorer need a patch-feature checkpoint: with a
pixel-resolution checkpoint, `/query` returns 409 for uncertainty/hybrid and runs
diversity/SOM without model scores (`model_iteration: null`, explained in
`notes`), while the SOM explorer returns `model_iteration: null` with
`model_note` instead of failing.

Training accepts `"evaluation_strategy": "spatial"` to attempt a block-grouped
holdout (256 px blocks of the patch origin, counted as `held_out_groups`); with
insufficient independent blocks the response labels the result
`insufficient_train_metrics`, sets `evaluation_warning`, and marks the metrics as
in-sample fit, not independent validation. The default `random` strategy is a
stratified random holdout with a fixed `random_state`. Blocks are a coarse proxy:
adjacent blocks share a boundary, so spatial grouping reduces — but does not
prove the absence of — spatial leakage. Per-class metrics include IoU and support,
so an absent class is visible instead of looking like a perfect score. Neither
strategy is a claim of improved accuracy.

Labels with `coordinate_space: "map"` are interpreted in the dataset's own CRS;
this is not an implicit WGS84 conversion. Point labels outside the selected
raster are rejected. Polygon labels must be closed finite rings and overlap the
dataset. `LICENSE` applies to repository code only; third-party components keep
their own licenses, which require a separate redistribution review.

## Reproducibility: content identity, manifests, artifact integrity

A score is only meaningful next to the data that produced it.

- **Inputs have content identity.** Dataset and scene uploads record the SHA-256
  and size of the exact bytes written. A legacy upload has `null` and is reported
  as "not recorded", never hashed after the fact.
- **Every new run carries a manifest** (`run-manifest-v1`): per-input content
  hashes, grid and band schema, the exact **label versions** trained, the taxonomy
  snapshot, the full configuration (model, resolution, seed, split protocol,
  bands), package versions and the code revision. Serialisation is canonical
  (sorted keys, compact, no NaN), so equal content always hashes equally.
- **Manifests exclude secrets and machine paths** — absolute paths shrink to a
  basename, `token`/`password`/`api_key` keys are dropped.
- **Artifacts are verified.** Checkpoints and exports record a checksum at write
  time; downloads verify it and answer `X-RSAL-Export-Integrity`. A modified or
  missing artifact is a 409 that names the problem, not a silent download.
- **Runs are grouped, not rewritten.** Experiments hold run membership only;
  creating, joining, leaving or deleting an experiment never alters a manifest or
  a metric.
- **Comparisons state their own validity.** `GET /projects/{id}/compare` lists
  metrics beside the fields that differ (inputs, label snapshot, config, protocol,
  environment) and sets `comparable: false` when the runs are not a controlled
  comparison — including when a run predates manifests.
- **No bitwise claim.** The environment is recorded so a rerun can be explained;
  identical results across different library or hardware versions are not
  promised.

## Temporal water mapping: native grids, areas, change and late fusion

Scenes registered under a project can now be classified and compared. The
governing rule is that **nothing is resampled unless someone explicitly says so,
and every number states the grid and the method behind it**.

### Classify one scene on its own grid

```bash
curl -X POST localhost:8000/projects/1/scenes/3/classify \
  -H 'content-type: application/json' \
  -d '{"method": "entropy"}'
```

- The scene is read on its **native affine**; hard, probability and uncertainty
  GeoTIFFs are written there, each with a recorded SHA-256, and the whole run is
  stored as an immutable `scene_analyses` row (grid, classes, band contract,
  study-area rule, artifacts, area summary, lineage digest).
- **Band identity must be provable.** The model's declared band schema is compared
  with the *scene's own* declared band names (band descriptions, or polarization
  when the count matches). A matching band count is never enough — a Sentinel-1
  GRD and a Sentinel-2 stack can both have four bands and mean different things.
  Unprovable identity is a `422` unless the caller records an explicit
  `accept_unverified_schema: true` override.
- The project study area is applied with the pixel-centre rule the dataset path
  uses, and the rule is stored with the record.
- `GET /projects/1/scenes/3/analyses` lists every classification (oldest first);
  a re-classification is a *new* record, never a rewrite.
- `GET /projects/1/analyses/4/exports/hard|probability|uncertainty` re-verifies
  the checksum, reopens the file to prove it is still on the recorded grid, and
  checks the source scene bytes still match their recorded hash. Tampering is a
  `409`; the record stays as written.

### Areas that state their method

`app/services/area_service.py` has exactly two honest answers:

| CRS | Method | Recorded as |
| --- | --- | --- |
| Projected, known linear unit | `\|det(affine)\| × (metres per unit)²` | `kind: "projected"`, `unit`, `pixel_area_m2` |
| Geographic | Exact WGS84 ellipsoid integration per pixel row | `kind: "geographic"`, `ellipsoid: "WGS84 (assumed)"`, `varies_by_row`, row min/max |
| Projected with an unconvertible unit, or no CRS | none | areas reported `available: false` with the reason |

Every area table carries its **valid denominator**: invalid/no-data pixels are
excluded from both the numerator and the total, `coverage` is reported, and a
binary water total is only produced when the run's taxonomy snapshot names the
water classes.

### Per-date series and change

```bash
curl localhost:8000/projects/1/temporal/series

curl -X POST localhost:8000/projects/1/temporal/compare \
  -H 'content-type: application/json' \
  -d '{"before_scene_id": 3, "after_scene_id": 4}'
```

- The series reports per-date class/water areas computed **natively per scene**,
  and lists differing grids or taxonomies as caveats instead of quietly
  reconciling them.
- The comparison returns a transition matrix, changed/unchanged areas and the
  denominator `"pixels valid in both dates"` — a change in cloud cover cannot
  masquerade as a change in water.
- **Mismatched grids fail closed.** The response is
  `409 {"error": "grid_mismatch", "differences": [...], "resampling_options": ["nearest"], "hint": ...}`
  naming every differing field.
- Alignment happens only on request: pass `"reference_scene_id"` (one of the two
  scenes). It is nearest-neighbour, recorded in `alignment` and in
  `lineage.comparison_digest`, and the native products are untouched.

### Late fusion only

```bash
curl -X POST localhost:8000/projects/1/fusion \
  -H 'content-type: application/json' \
  -d '{"rule": "weighted_probability", "target_scene_id": 3,
       "analysis_ids": [1, 2], "weights": {"Sentinel-1": 0.6, "Sentinel-2": 0.4},
       "missing_policy": "require_all"}'
```

- The **target grid is a real scene's grid**, declared in the request and stored
  with the result.
- Rules: `weighted_probability`, `weighted_vote`, `priority`. Missing-data
  semantics are explicit: `require_all` (a pixel is fused only where every source
  is valid) or `renormalise` (weights are renormalised over the sources available
  at each pixel). The chosen semantics are stored verbatim in the record.
- Per-sensor results are **preserved**, not replaced: each source analysis id,
  sensor, weight, alignment flag and analysis digest is part of the fusion record,
  alongside agreement statistics (unanimous share, per-source agreement).
- `early_fusion` / `raw_band_fusion` are refused with a structured `422`
  (`early_fusion_rejected`): combining raw bands across sensors would need a
  harmonisation step this engine does not implement, and the result could not be
  decomposed back into per-sensor evidence.

### In the research workspace

The **Temporal Analysis** page now shows per-date result cards (native-grid badge,
area method, class and water areas, verified downloads), a per-date series table
with its caveats, a change panel that offers explicit alignment only after the
engine reports a grid mismatch, and a fusion panel listing per-source weights,
alignment and agreement. **Results & Evaluation** gained a "Single-sensor vs fused
products" panel so a fused number is always read next to the per-sensor evidence.

## Research evaluation: protocols, benchmarks and reports

Phase 5 turns "the model scored 0.87" into a claim that can be audited, or refuses to
make it.

### A protocol is a record, not a seed in a request

```bash
POST /projects/{id}/research/protocols
{"protocol": "spatial", "seed": 7, "block_size": 256, "buffer": 32}
```

| kind | holds out | leak it prevents |
| --- | --- | --- |
| `random` | stratified samples by seed | none — the honest baseline, reported as such |
| `spatial` | whole blocks, keyed `block:{dataset_id}:{row}:{col}`, buffer in pixels | neighbouring-patch correlation across the boundary |
| `temporal` | entire acquisition groups | using the same date/scene on both sides |

The response carries the full split membership, the held-out groups and a `split_hash`
over the canonical split. A split the data cannot support is stored as `insufficient`
with a reason — never silently downgraded to a random split, and never reported as a
score. Spatial blocks include the dataset id, so two rasters sharing the same block
coordinates are not mistaken for one.

### Scoring only happens on the held-out partition

`POST /projects/{id}/research/evaluations` refits a fresh model on the training
partition and scores the held-out partition only; the production model is not reused
(it has seen every labelled sample). Results keep a stable class order with per-class
support, and any undefined metric is `null` with a per-class reason — a class that was
never predicted gets `precision: null`, not `1.0`. Calibration (ECE, maximum CE,
Brier) and a coverage curve are reported with their sample count, method and a
"held-out only" caveat, or `available: false` with the reason.

### Area error needs truth the engine did not produce

```bash
POST /projects/{id}/research/reference-areas
{"water_area_m2": 25000, "source": "field survey 2026-01", "method": "GNSS shoreline survey"}
```

`area-error` answers `409` until both a reference area **and** a classified scene
exist. Without one, mapped areas are labelled estimates and no error metric is
reported. `scene-spread` refuses to pool pixels and aggregates per scene, stating the
resampling unit.

### Comparisons declare their controls

A `ResearchPlan` records factors, levels, repetitions, comparison metric and holdout
protocol before any run. `plans/compare` returns the shared and differing factors plus
a `paired` verdict, which is `false` whenever the results were not scored on the same
persisted split — the response then says so in its caveats rather than presenting the
numbers as a controlled comparison.

### Reports are regenerable views of stored records

`POST /projects/{id}/research/reports` writes JSON, CSV and Markdown with per-artifact
`sha256`/`size_bytes` and a canonical digest. Volatile fields (`created_at`, `path`,
storage references) are stripped **and** `datetime`/`Decimal`/numpy scalars are coerced,
so a regeneration from the same records hashes identically. Downloads re-verify the
checksum; a tampered file is refused with `409`. Runs that predate manifests are listed
as excluded with the reason instead of being dropped.

`GET /projects/{id}/research/status` keeps the two questions apart:

```
software_validation : "verified by automated tests on synthetic data"
scientific_validity : "not established"
```

### In the research workspace

**Results & Evaluation** gained a research panel: the software/science status pair,
protocol declaration and a protocol table showing train/test counts, the split hash and
any insufficiency reason, held-out evaluation cards with per-class support and
null-with-reason rows, calibration and dropped-sample counts, reference-area entry
(source and method mandatory), plan comparison with the pairing verdict, and report
generation with digest, artifact downloads and the stated limitations.

## Sampling history and annotation provenance

Active-learning selections are no longer a browser artefact. Every successful
query writes a durable batch and its items, in one transaction:

| Recorded | Why it matters |
| --- | --- |
| Project, dataset, strategy, method, `strategy_version` | Which rule produced this selection |
| Seed — **only** for `strategy=random` | A deterministic strategy has no seed to claim |
| Candidate pool: patch size, stride, grid, labeled count, eligibility rule, ordered SHA-256 hash | Two batches are provably comparable, or provably not |
| Model iteration / training run | What knowledge the pool was sampled with |
| Per item: `pending`, `labeled`, `rejected`, `deferred` + time and note | A rejection is a decision, not silence |

- `strategy=random` is the **seeded baseline**: same valid, unlabeled pool,
  without replacement, repeatable from the recorded seed.
- `GET /projects/{id}/queries` lists batches (newest first, with decision counts)
  and `GET /projects/{id}/queries/{batch_id}` reopens one with identical item
  identities and order, from any browser.
- A label submitted from a query item links that version to the item
  (`labels.query_batch_id` / `query_item_id`). `LabelOut.provenance` reads
  `query` only when that link exists; typed and legacy labels report `manual`.
- **No accounts, no collaboration claims.** Batches are project-scoped. A batch
  records what was sampled, never who sampled it; `note` is free text, not an
  author field.
- Batches are append-only history: there is deliberately no delete endpoint.

## Water taxonomy and the derived binary product

A WBALC project is not just "some classes". Creating one with the default water
taxonomy records a versioned snapshot:

| Piece | Value |
| --- | --- |
| Taxonomy version | `wbalc-water-taxonomy-v1` |
| Internal classes (order is identity) | `open_water`, `emergent_vegetation`, `land` |
| Label crosswalk | every class ID, plus only the aliases the project configured |
| Binary interpretation | `water_vs_non_water` or `open_water_vs_other` |

- **Aliases are explicit configuration.** `reed` is *not* a synonym for emergent
  vegetation unless the project says so (`label_aliases`). Submitting an unmapped
  term is a **422** that names the project's classes and, where possible, the
  closest configured ones. When an alias *is* used, the resolved class and the
  original submitted text are both kept (`labels.submitted_class_name`).
- **Generic projects opt out on purpose.** `GET /projects/{id}/taxonomy` says
  `source: "legacy"` for a project created with `generic_classes: true`; such a
  project keeps its own class list and gets **no** derived water product.
- **The three-class map is the source product.** `/download/binary` (1 = water,
  0 = other) and `/download/binary_probability` (P(water)) are *derived* files with
  `derived=true`, the exact mapping and the source run in their tags. Neither
  overwrites or collapses the three-class output, and `layer=binary` on the map is
  that same derivation, not a second model.
- **Absent classes are reported, not fabricated.** If the model never learned a
  class the interpretation needs, the plan comes back `available: false` with the
  missing class named, no binary file is written and no download link is offered.
- **Semantics are frozen per run.** The taxonomy snapshot travels with the run and
  the checkpoint; changing the project's interpretation afterwards does not rewrite
  what an existing model means — a new run is required.

## Band identity and the study-area mask

Band *count* is not band *identity*. A four-band stack can be blue/green/red/nir in
one order and something else entirely in another, so the engine refuses to treat
equal widths as proof of compatibility:

- **Declaring a schema.** Uploads accept `band_names` (comma-separated, one per
  band) and `sensor` as form fields. Named bands in the file's metadata
  (`descriptions`, `NAME`/`BAND_NAME` tags) are used otherwise. A schema is
  `declared` only when *every* band is named; a partially named stack is
  undeclared, and a band-count match alone never verifies anything.
- **Training.** All contributing rasters must share one declared, identically
  ordered schema. Mixed or unnamed inputs are refused with **422**; passing
  `"accept_unverified_schema": true` records `schema_override` on the run instead.
- **Inference.** `POST /predict` requires an explicit `dataset_id` — there is no
  "latest dataset" fallback — and validates project ownership. If the reference
  raster cannot be proven to carry the model's ordered bands, the request fails
  with **409** and a reason (`ordered band names differ (...)`, `the selected
  raster's bands are unnamed`, `band schema digests differ`, ...). Repeat with
  `?accept_unverified_schema=true` to record an explicit override. Every response
  and GeoTIFF carries `band_schema_verified`, `band_schema_reason` and
  `schema_override`.
- **Study area.** When a project has a `study_area_geometry`, predictions and all
  exports are valid only where *both* the pixel centre is inside the polygon and
  every source band is valid. The geometry is transformed (vector coordinates
  only, via `rasterio.warp.transform`) from the project CRS into the raster CRS —
  never a raster reprojection. Missing CRS or a failed operation is a **422**
  (`Study area cannot be applied: ...`). NoData is written outside the mask in
  hard, probability and uncertainty alike, and the products carry
  `study_area_applied`. Patch-cell products are masked at cell resolution and say
  so. The source GeoTIFF is never modified.

## Resource bounds

`MAX_RASTER_ELEMENTS` (default 250,000,000) is a **count of float32 elements the
engine would have to hold at once**, not a throughput promise and not a file-size
limit. It is checked *before* the array is allocated, and the refusal names the
numbers, the setting and the ways out (`region` windows, patch resolution, or
raising the limit knowingly):

```
per-pixel classification needs 4x10000x10000x3 = 1,200,000,000 float32 elements,
over the configured limit of 250,000,000 (MAX_RASTER_ELEMENTS). The extra factor is
the number of class-probability bands produced per pixel. Nothing was allocated.
Predict a window with `region`, use patch resolution instead of per-pixel
inference, or raise MAX_RASTER_ELEMENTS knowingly.
```

| Path | What is held in memory | Counted factor |
| --- | --- | --- |
| `GET /download/*` / patch inference | whole source cube (bands × H × W) | ×1 |
| Per-pixel inference | source blocks + full probability cube | × classes |
| Pixel training extraction | 256×256 blocks only (never the full cube) | ×1, checked first |
| SOM / `/query` | whole source cube | ×1 |

Uploads are separately capped by `MAX_UPLOAD_BYTES` (512 MiB). Per-pixel inference
is *not* out-of-core: blocks are read incrementally, but the probability cube for
the requested window is materialised, so the limit scales with classes.

## Known limitations

- **Patch-mode rasters are cell maps, not pixel classifications.** Each cell's
  value is replicated over its pixel window; do not read per-pixel structure into
  them. Use `resolution: "pixel"` when per-pixel predictions are required.
- **Rotated/skewed rasters** are exported by copying the source affine verbatim
  (they stay correctly georeferenced), but the PNG previews and the browser
  overlay are north-up pictures of the cell grid. There is no resampling path.
- **No streaming inference.** Pixel inference reads the source in 256×256 blocks
  but keeps the full probability cube in memory; `MAX_RASTER_ELEMENTS` is the only
  guard, and training is synchronous. See *Resource bounds* for exactly what is
  counted.
- **Spatial evaluation is block-based** (256 px boxes) and is not buffered against
  boundary leakage.
- **The review queue lives in the browser** (`localStorage`, zustand persist).
  Pending suggestions survive a refresh on that browser/profile, but they are not
  shared between browsers and are lost if site data is cleared; labels are only
  durable once submitted to `/labels`.
- **Geographic-CRS areas assume WGS84.** A geographic grid's pixel areas are
  integrated on the WGS84 ellipsoid; the response records that assumption, and a
  geographic CRS on another ellipsoid would bias the numbers.
- **Temporal change needs one class order.** Two dates classified by runs with
  different class lists are refused (409) rather than remapped; alignment is
  nearest-neighbour only, and there is no "classify all scenes" batch job.
- **Pixel-mode training is API-only.** The workspace trains patch models; its
  adapter forwards `resolution`/`evaluation_strategy` when a caller supplies them.
- **Unsupervised SOM** still loads the full raster and uses at most
  `max_train_samples` observations for the fit; its cluster map is a
  nearest-neuron assignment, not a supervised classification.
- **Checkpoints are joblib files** written by the server. There is no upload
  endpoint for them, and loading validates format/keys/classes/bands/resolution
  but is not a sandbox for hostile files on disk.

## Design decisions (resolving the proposal's open questions)

- **Patch grid**: 32×32 px windows, stride = patch size (non-overlapping) by
  default; configurable via `PATCH_SIZE` / `STRIDE` and per-query overrides.
  The last row/column is clamped to the image edge so the full extent is covered.
- **Embeddings**: per-band mean/std/min/max patch statistics (4 × bands features)
  feed both the classical models and the diversity/core-set strategy.
- **Diversity**: greedy k-center (farthest-first) over standardized embeddings,
  seeded with already-labeled patches when available.
- **Hybrid**: top `batch_size × 5` uncertainty pool, then k-center within the pool.
- **Self-organizing map (SOM)**: PCA-initialized batch Kohonen SOM over standardized
  patch embeddings with U-Matrix boundary distances, quantization & topographic
  error metrics, per-neuron spectral prototypes, and topological active-learning
  sampling (`strategy: "som"`, including single-neuron `som_cell` targeting).
- **Evaluation**: stratified random hold-out when data allows (≥8 samples, ≥2
  per class) or a block-grouped spatial hold-out on request; otherwise
  training-set metrics flagged `insufficient_train_metrics` with a warning. The
  deployed checkpoint is always refit on all labeled data.
- **Synchronous training** runs in a thread pool with a raster-size guard rail
  (`MAX_RASTER_ELEMENTS`); migrate to Celery + Postgres for production scale.

## Project layout

```
app/
  main.py            # FastAPI factory, lifespan (init_db), CORS
  config.py          # env settings (.env supported)
  db.py              # async engine/session, init_db
  models.py          # Project, Scene, Dataset, Label, TrainingRun, Export
  schemas.py         # Pydantic request/response models
  storage.py         # STORAGE_DIR layout helpers
  migrations/        # numbered additive database schema migrations
  api/               # routers: projects, scenes, datasets, labels, query, training, inference
  services/          # raster/grid, AL strategies, label resolution, training, export
tests/               # backend unit/API tests incl. synthetic multi-sensor scenes
scripts/demo.py      # end-to-end AL loop against a live backend
frontend/  # bilingual SvelteKit workspace
scripts/research_frontend_smoke.py             # end-to-end loop through the workspace adapter
openspec/            # spec-driven change proposals + capability specs
```

## Tests

```bash
.venv/bin/python -m pytest
```

`tests/test_end_to_end_workflow.py` is the integrated gate: one synthetic scene from
ingest through query/labels, training, inference, lineage, temporal analysis and fusion
to a held-out evaluation and a regenerable report bundle.

The suite now covers project CRUD, legacy dataset workflows, labels, Active
Learning, training/inference/exports, synthetic multi-temporal scenes (Sentinel-1/2
metadata, NoData/masks, optional dates, grid differences, ordering, isolated deletion,
API responses), research protocols (random/spatial/temporal disjointness, buffer
reach, insufficiency), held-out metric semantics, reference-area guards, report
regeneration, and migration of an RSAL-style project database (versions 1…10).

The SvelteKit workspace has its own suites:

```bash
cd frontend
npm run check          # svelte-check + TypeScript
npm test               # Vitest: geometry, adapter shaping, i18n, jsdom components
npm run check:i18n     # en/fa dictionary completeness + placeholder parity
```

Its browser-facing contract is verified end-to-end (project → upload → query →
label → train → metrics/map/exports → scenes → import → delete → protocols →
held-out evaluation → reference area → plan comparison → report bundle → i18n) by
`scripts/research_frontend_smoke.py`, which needs a live engine and the
workspace running against it.

`scripts/audit_performance.py` measures the same app against a live engine
(adapter overhead, raster streaming, query/train/inference cost, SSR) and
produces the tables in [`PERFORMANCE.md`](PERFORMANCE.md).
