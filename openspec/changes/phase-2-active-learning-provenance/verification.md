# Verification — phase-2-active-learning-provenance

Date: 2026-11-18. Branch: `arena/a4a6bd6b-wbalc`. Every command below was run in
this workspace; nothing is called verified without its output.

## What shipped

### Durable batches (no auth, no pretence of it)

- New tables `query_batches` and `query_items` (migration **v006**, additive,
  created with `checkfirst`, so existing databases simply gain them).
- Every successful `POST /projects/{id}/query` persists, atomically with its
  items:
  - project, dataset, strategy, method, `strategy_version` (`query-v1`);
  - `seed` (**only** for `strategy=random`; deterministic strategies store NULL
    rather than a seed they never used);
  - requested vs returned size, model iteration, training run, notes;
  - the **candidate pool**: patch size, stride, grid, grid cell count, how many
    patches were already labeled, the eligibility rule
    (`valid-source-pixels` [+ ` and unlabeled`]) and a SHA-256 hash of the
    *ordered* eligible sample ids.
- The pool hash makes two batches provably comparable: a random baseline and a
  diversity batch over the same scene report the same hash (asserted end-to-end).
- A refusal (e.g. uncertainty with no model → 409) happens before persistence, so
  history never shows a phantom batch.
- `GET /projects/{id}/queries` (newest first, decision counts) and
  `GET /projects/{id}/queries/{batch_id}` (full items in recorded order) are
  project-scoped. There is **no delete endpoint**: a batch is history.

### Seeded random baseline

- `strategy=random` samples without replacement from the same pool every other
  strategy uses, via `np.random.default_rng(seed).permutation(n)`; the default
  seed is the engine's `random_state` and is always recorded.
- Repeatability is tested at the unit level (same seed → same indices, no
  duplicates, pool shorter than the batch) and end-to-end (two requests with the
  same seed return the same samples in the same order under different batch ids).

### Decision state and label linkage

- `query_items.status` ∈ `pending | labeled | rejected | deferred`, with
  `decided_class`, `decided_at`, `decision_note`, `label_id`, exposed through
  `PATCH /projects/{id}/queries/{batch_id}/items/{item_id}`.
- Submitting a label with `query_batch_id`/`query_item_id` links that label
  version to the item, marks it `labeled`, and stores `labels.query_batch_id` /
  `query_item_id` (migration v006).
- Mismatches are refused with a 422 that says why: the item belongs to another
  batch, another project, or a *different sample* than the label resolves to.
- `LabelOut.provenance` is `query` only when that link exists, otherwise
  `manual`. Legacy and typed labels are never attributed to a query.

### UI

- Adapter: `toQueryBatch` now carries `batchId`, `seed`, `strategyVersion`,
  `requestedSize`, `trainingRunId` and the pool; new `toQueryItem`,
  `toQueryHistory`; `toLabel` carries `provenance`/`submittedClassName`.
- New routes: `/api/projects/{id}/queries`, `/api/projects/{id}/queries/{batchId}`,
  `PATCH .../items/{itemId}`.
- Learning page: `Random (baseline)` strategy with an optional seed field, a
  *Selection provenance* bar (batch id, strategy/method, seed, model, pool
  size/hash), a *Sampling history* list with resume, a *Reject suggestion* action
  next to *Skip* (both persisted as durable decisions), and label submission that
  sends the query item ids so the engine records the link.
- `ReviewState` now stores `batchId`; `loadBatch()` rebuilds submitted decisions
  from the engine and **drops browser-only drafts**, so a resumed batch never
  claims a draft was submitted.
- i18n: 379 keys in `en` and `fa` (was 355).

## Commands and results

```
$ .venv/bin/python -m pytest -p no:warnings
243 passed in 64.25s
```
(217 after Phase 1 → 243; 26 new tests in `tests/test_active_learning_phase2.py`.)

```
$ npx svelte-check --tsconfig ./tsconfig.json
svelte-check found 0 errors and 0 warnings

$ npx vitest run
Test Files  5 passed (5)
     Tests  54 passed (54)

$ node scripts/check-i18n.mjs
✔ i18n complete: 379 keys in en.ts and fa.ts
```

```
$ .venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
88 checks passed
```
New end-to-end checks (was 75): batch identity + pool, "deterministic strategy
records no seed", seeded random baseline, random/diversity sharing one pool hash,
repeatability across requests, newest-first history, reopening a batch with the
same items and order, durable rejection → deferral transitions with counts,
label-answered-from-item recording `query` provenance, typed labels reporting
`manual`, and the item flipping to `labeled` with the right `labelId`.

## Not verified / deliberately open

- **No collaboration claim.** There is no authentication, so batches store no
  author, no permissions and no "shared workspace" language. `note` is free text
  and is not presented as an identity.
- **Candidate selection stays patch-grid based.** Pixel-level active learning is
  out of scope for this phase; the pool description says `patch_size` explicitly.
- **Resuming a batch does not re-run selection.** The recorded items are shown as
  they were selected; if the dataset or labels have changed since, the pool hash
  will no longer match a fresh query, which is the honest way to see the drift.
- **Browser drafts are dropped on resume by design** — they were never submitted.
- **The `som_cell`/SOM-targeted path** still bypasses the strategy block; it
  produces a normal batch record but the tested strategies are uncertainty,
  diversity, hybrid, som and random.
- **Manual visual check** of the history panel/provenance bar remains a human
  task (Playwright cannot be installed here).
