# Proposal

## Why

The WBALC engine (RSAL backend + Next.js TerraLab frontend) is functional, but the repository also contains a richer, research-oriented SvelteKit interface (`examples/wbalc-geospatial-research-interface/`) that ships entirely on simulated data and has no backend connection. It offers six research views (overview, geospatial workspace, temporal analysis, active learning, model arena, results & evaluation) that map well onto RSAL capabilities, plus an offline Leaflet map, charts, and browser-local review state. Today it is a demo only: every observation, sample, metric and prediction is hardcoded, and it is English-only.

This change turns that demo into a second, fully working frontend example that runs against the real RSAL engine, and makes it bilingual (Persian/Farsi and English) with proper RTL support. It gives researchers a lightweight SvelteKit alternative to the Next.js workspace without duplicating the backend, and exercises the same RSAL contracts from a different client stack.

## What Changes

- Relocate `wbalc-geospatial-research-interface/` to `examples/wbalc-geospatial-research-interface/` as a frontend example (done).
- New `examples/wbalc-geospatial-research-interface/` app rebuilt RSAL-only: replace all hardcoded research data (observations, samples, models, metrics, confusion matrices) with live calls through a thin SvelteKit server-side adapter (BFF) to RSAL (`RSAL_API_URL`, server-side only).
- Map the six research views onto RSAL entities: projects/datasets/scenes drive overview, geospatial workspace and temporal analysis; query/labels drive active learning; training/metrics drive model arena and results & evaluation.
- Preserve the offline Leaflet map and band rendering by fetching original GeoTIFF bytes through the RSAL file endpoint via the adapter, with pixel-space fallback for non-georeferenced rasters.
- Client-persisted review queue and drafts (per project) stay browser-local; submitted labels are real RSAL labels.
- Bilingual UI: full Persian (Farsi) and English with runtime language switch, RTL layout for Persian, locale-aware date/number formatting, and persisted language preference.
- Additive backend work only if gaps surface (reuse existing endpoints: projects, datasets incl. file download, labels, query, train, metrics, scenes). No changes to existing RSAL response shapes.
- Docker compose and root README document the example app and its env vars.
- Verification: typecheck/build green, live end-to-end smoke through the adapter, bilingual smoke (RTL/LTR).

## Capabilities

### New Capabilities
- `geospatial-research-workspace`: the SvelteKit research workspace wired to the real RSAL engine (six views, real data, offline map, client-persisted review queue).
- `frontend-i18n`: bilingual (Persian/English) UI capability with runtime switching, RTL/LTR layout, locale-aware formatting and persisted preference.

### Modified Capabilities
- None. Existing RSAL endpoint contracts and the TerraLab `frontend-workspace` capability are unchanged; this is an additional frontend example.

## Impact

- New example codebase under `examples/wbalc-geospatial-research-interface/` (SvelteKit 5, Svelte 5 runes, Vite, Tailwind v4, Leaflet, TypeScript).
- Thin server-side adapter routes inside the example app proxying to RSAL; no new backend DB or ORM.
- Reuses existing RSAL endpoints (including dataset file download, metadata, deletion, label deletion) and scene/multitemporal data.
- Documentation: root README section + example README update; optional compose service profile.
- No breaking changes to RSAL; existing tests remain valid.
