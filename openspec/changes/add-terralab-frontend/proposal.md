## Why

The RSAL backend is complete and merged, but has no user-facing UI. Two candidate
frontends were added to the repo (`satellite-active-learning-frontend` "TerraLab"
and `satellite-image-classification-frontend` "TerraLoop"). Both ship simulated
demo backends (PostgreSQL + Drizzle + fake training) and API contracts that do
not match RSAL. Neither works against the real backend out of the box.

Decision (product owner): TerraLab's design is the winner. Build one new
frontend in `frontend/` from TerraLab's design system, port TerraLoop's useful
extras (label import, review keyboard shortcuts, analytics CSV export, label
edit/delete), wire everything to the real RSAL API, and delete both source
folders once parity is verified.

## What Changes

- New `frontend/` app: TerraLab workspace (sidebar/topbar shell, projects,
  datasets, learning, analytics views) rebuilt RSAL-only.
- Remove the simulated demo backend entirely: no PostgreSQL, no Drizzle, no
  fake training. All data comes from RSAL through a thin Next.js server-side
  adapter (BFF) that translates TerraLab view models to/from the RSAL contract.
- Port from TerraLoop: GeoJSON/CSV label import, keyboard-driven batch review,
  analytics CSV export, label correction/deletion UI.
- Backend additions required by the UI (small, additive):
  - Serve the original GeoTIFF bytes so the browser can render bands/NDVI.
  - Extended dataset metadata (file size, patch-grid dimensions).
  - Dataset deletion (with associated labels/exports cleanup).
  - Label deletion (all versions of a sample).
- Review queue becomes client-persisted (RSAL queries are stateless); skips and
  drafts stay local, submitted labels are real RSAL labels.
- Docker compose gains a `frontend` service; root README documents the app.
- Delete `satellite-active-learning-frontend/` and
  `satellite-image-classification-frontend/` after verification.

## Capabilities

### New Capabilities
- `frontend-workspace`: the TerraLab-designed, RSAL-backed labeling workspace.

### Modified Capabilities
- `dataset-ingestion`: raw file access, extended metadata, dataset deletion.
- `label-management`: sample label deletion.

## Impact

- New codebase under `frontend/` (Next.js App Router, React 19, Tailwind v4).
- Additive endpoints in `app/api/datasets.py` and `app/api/labels.py` + tests.
- `docker-compose.yml`, root `README.md`, `.env.example` updates.
- Removal of the two donor frontend folders (net large deletion).
- No changes to existing RSAL endpoint contracts; existing tests keep passing.
