# Verification — phase-3-experiment-lineage

Date: 2026-11-18. Branch: `arena/a4a6bd6b-wbalc`. Every command below was run here.

## What shipped

### Content identity (inputs)

- `datasets.content_sha256` / `size_bytes` and `scenes.content_sha256` /
  `size_bytes` (migration **v007**, additive). The hash is computed from the
  same chunks that are written to disk, so it describes the stored file rather
  than a second read of it. Source bytes themselves are never modified.
- `GET /projects/{id}/dataset` exposes `content_sha256`; the UI shows it in the
  raster panel and says "not recorded (legacy upload)" when it is absent instead
  of hashing today and pretending it was always known.
- Repeated uploads of identical bytes produce identical hashes; different bytes
  produce different hashes (tested).

### Reproducibility manifest (runs)

- `app/services/lineage_service.py`: canonical serialisation
  (`json.dumps(sort_keys=True, separators=(",",":"), allow_nan=False)`), SHA-256
  digests, secret-key scrubbing (`password`, `token`, `api_key`, …) and
  machine-path scrubbing (absolute paths → basename).
- Every new run persists `manifest` + `checkpoint_sha256`. The manifest contains:
  project classes, taxonomy snapshot, per-input content hashes/grid/band schema,
  the **exact label versions** trained (`label_id`, `sample_id`, `version`,
  `class_name`, `dataset_id`, query batch/item), the feature schema, the full
  config (model, resolution, seed, test size, split protocol, bands, patch size,
  stride, checkpoint hash), and the environment (python, platform, package
  versions, code revision).
- A corrected label creates a new label *version*, so the next run's label
  snapshot hash differs while the earlier run's manifest is byte-identical
  (asserted).
- `lineage_status` ∈ `complete | incomplete | legacy`; `missing` names what could
  not be recorded. A run with no manifest reads `legacy` and its unavailable
  fields are reported as such, never reconstructed.
- `GET /projects/{id}/runs/{run_id}/lineage` and `GET /projects/{id}/runs`
  expose this; artifacts are re-verified on request.

### Artifact integrity

- `exports.sha256` / `size_bytes` recorded right after the atomic write.
- `GET /download/{type}` verifies before serving: `X-RSAL-Export-Integrity`
  (`verified` / `unverified` for legacy artifacts) and `X-RSAL-Export-Sha256`.
  A modified or missing artifact is a **409 with the reason**, and the export row
  is left alone (tested by corrupting and restoring a real GeoTIFF).
- Checkpoint integrity is checked the same way through the lineage endpoint.

### Experiments

- New `experiments` table (migration v007) with name/description/hypothesis/config;
  membership is `training_runs.experiment_id`.
- `POST/PATCH/DELETE /projects/{id}/experiments`,
  `POST/DELETE …/experiments/{id}/runs`. Grouping writes **only** the
  association: the run manifest and metrics are untouched (asserted), and a run
  already in another experiment is a 409 rather than a silent move. Deleting an
  experiment detaches runs and keeps all history.
- `GET /projects/{id}/experiments/{id}/compare` and `GET /projects/{id}/compare?run_ids=…`
  return per-run metrics **plus** input hashes, label snapshot hash, config,
  evaluation protocol and environment revision, with a `differences` map,
  `caveats` and a `comparable` flag that is false when inputs/labels/config/
  protocol differ, when any run is legacy, or when fewer than two runs are in
  scope.

### UI

- Evaluation page: a *Reproducibility record* panel (status, manifest hash, label
  snapshot hash, per-input hashes, checkpoint verification, code revision,
  explicit "Not recorded:" list) and an *Experiments* panel (create with the
  current run, pick a group, add the current run, comparison table with lineage
  status and a plain-language verdict plus the list of differences and caveats).
- Adapter: `toRun` now carries `manifestHash`/`lineageStatus`/`experimentId`/
  `checkpointSha256`; new `toRunLineage`, `toComparison`, `toExperiment`.
- i18n: 412 keys in `en` and `fa` (was 379).

## Commands and results

```
$ .venv/bin/python -m pytest -p no:warnings
269 passed in 76.01s
```
(243 after Phase 2 → 269; 26 new tests in `tests/test_lineage_phase3.py`.)

```
$ npx svelte-check --tsconfig ./tsconfig.json
svelte-check found 0 errors and 0 warnings

$ npx vitest run
Test Files  5 passed (5)
     Tests  59 passed (59)      (was 54: 5 new lineage/comparison adapter tests)

$ node scripts/check-i18n.mjs
✔ i18n complete: 412 keys in en.ts and fa.ts
```

```
$ .venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
99 checks passed
```
New end-to-end checks (was 88): content hash exposed by the adapter, run list
reporting lineage completeness, lineage naming inputs + label snapshot,
checkpoint verification, environment/config present, no machine paths in the
manifest, artifact checksum + integrity verdict on exports, experiment grouping
without touching the run, single-run comparison refusing comparability, and
experiment detail carrying membership.

## Not verified / deliberately open

- **No bitwise-reproducibility claim.** The manifest records the environment so a
  rerun can be *explained*, but identical floats across different library or
  hardware builds are not asserted anywhere.
- **Storage paths are excluded from manifests by design** (basename only), so a
  manifest cannot be used to locate a file on another machine — that is the
  intended trade-off, not an oversight.
- **Legacy data keeps NULL identities.** Datasets uploaded before this change are
  never hashed retrospectively, and their runs report `legacy`/`incomplete`.
- **Scene content hashes** are recorded but the lineage manifest currently covers
  training *datasets*; scenes are inputs to future temporal products (Phase 4).
- **Export integrity is checked at download**, not continuously; a corrupted file
  is caught the next time it is served.
- **Manual visual check** of the new lineage/experiment panels remains a human
  task (Playwright cannot be installed here).
