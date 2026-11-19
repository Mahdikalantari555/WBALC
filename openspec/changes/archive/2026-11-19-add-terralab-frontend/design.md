## Context

RSAL exposes a clean spec-driven REST API (projects, datasets, labels, query,
train, metrics, predict/export). TerraLab offers the preferred design system
and workspace UX but expects a different contract (class objects with colors,
persistent sample queue, rich project stats, raw raster URLs) backed by a
simulated PostgreSQL demo. TerraLoop has a weaker design but useful features.

## Goals / Non-Goals

**Goals:** one production frontend in `frontend/` using TerraLab's design,
100% real RSAL data, TerraLoop's extras, verified end-to-end, donors deleted.
**Non-Goals:** no local database, no simulated training, no changes to existing
RSAL response shapes, no multi-user/auth, no async job queue.

## Decisions

- **BFF adapter, backend contract untouched.** Next.js route handlers under
  `frontend/src/app/api/` proxy to RSAL (`RSAL_API_URL`, server-side only) and
  translate view models. Existing RSAL specs/tests remain valid; all UI-specific
  shaping lives in the adapter.
- **Class colors** are assigned deterministically by index from a fixed palette
  in the adapter; RSAL classes stay `string[]`. Class id = class name.
- **Project stats** (iteration, accuracy, F1, labeled count, total patches) are
  assembled in the adapter from `/metrics`, `/labels`, `/dataset` (parallel
  requests). Display status derives: no labels → unlabeled, labels → in_progress,
  RSAL status "completed" → completed.
- **Review queue is client-state.** RSAL `/query` is stateless; the returned
  batch lives in a persisted Zustand store (per project). Skips and notes are
  local-only; submitting writes real labels via RSAL. No `/predictions` endpoint
  is emulated server-side.
- **Strategy mapping:** UI entropy/margin/least_confidence → RSAL
  `strategy=uncertainty` + `method`; diversity/hybrid map 1:1. Cold start offers
  diversity (RSAL returns 409 for model-dependent strategies without a model;
  the adapter surfaces an actionable message).
- **Coordinates:** RSAL query samples carry pixel + CRS coords. The adapter
  reprojects CRS→WGS84 (proj4) for Leaflet when the dataset is georeferenced;
  otherwise the map falls back to pixel space (Leaflet CRS.Simple). Drawn/imported
  WGS84 geometries are converted back to dataset pixel space before submission.
- **Raster rendering** stays client-side (geotiff.js) fetching original bytes
  from the new RSAL file endpoint via the adapter; band modes RGB/false-color/
  NDVI/custom unchanged from TerraLab.
- **Backend additions are minimal:** file download, computed metadata
  (size via file stat, patch grid from settings — no DB migration), dataset
  delete (removes file, labels, exports for that dataset), label delete
  (all versions of a sample_id).
- **Analytics:** learning curve + confusion matrix + per-class from RSAL
  metrics/history; class distribution from current labels. Confidence-drift
  chart (simulation-only in donors) is dropped rather than faked. CSV export
  ported from TerraLoop.
- **Branding:** keep "TerraLab" name and visual identity.

## Risks / Trade-offs

- Adapter fan-out for project list stats is N+1-ish → acceptable at MVP scale;
  parallelized and cached by React Query. Can add a backend summary endpoint later.
- Client-persisted queue is per-browser → fine for single-analyst MVP; a future
  backend batch store can replace it without UI changes.
- Synchronous RSAL training blocks the train request → adapter timeout 120 s,
  UI shows progress state (matches current backend MVP design).
- Donor deletion is irreversible in-tree → history preserves both sources.

## Migration Plan

1. Land backend additions + tests (additive, no breaking changes).
2. Build `frontend/` from TerraLab sources; strip demo backend; wire adapter.
3. Verify: backend pytest, frontend typecheck/build, live API smoke through the
   adapter (create → upload → query → label → train → metrics → import → delete).
4. Compose service + docs.
5. Delete both donor folders.

## Open Questions (resolved by product owner)

- Scope: spec **and** full implementation in this change.
- Demo mode: dropped entirely (RSAL-only).
- TerraLoop extras: ported (import, shortcuts, CSV export, label edit/delete).
- Branding/location: keep "TerraLab", app lives in `frontend/`.
