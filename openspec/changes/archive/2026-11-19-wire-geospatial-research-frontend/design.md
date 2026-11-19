# Design

## Context

See proposal.md - Why. The example app lives at `examples/wbalc-geospatial-research-interface/` and is a SvelteKit 5 / Svelte 5 runes project with Vite, Tailwind v4, Leaflet and TypeScript. It currently renders six views from a single mock module (`src/lib/data/research.ts`) plus browser-local review state. The WBALC engine exposes a REST API (FastAPI) under `/projects`, `/projects/{id}/dataset`, `/projects/{id}/dataset/{id}/file`, labels, query, train, metrics, scenes. The existing Next.js `frontend/` already established the BFF adapter pattern and RSAL-only data flow; this change mirrors that pattern in SvelteKit.

## Goals / Non-Goals

**Goals:**
- Replace every mock data source with live RSAL data accessed through SvelteKit `+server.ts` route handlers.
- Preserve the existing UX (six views, offline map, band modes, review keyboard shortcuts, CSV export) while sourcing real data.
- Add bilingual (fa/en) UI with RTL for Persian, locale-aware formatting, persisted preference.
- Keep the example self-contained and optional (not required by compose by default).

**Non-Goals:**
- No backend schema changes or new RSAL endpoints unless a verified gap appears; reuse existing contracts.
- No multi-user/auth, no server-side persistence of review queues, no simulated training.
- No rewrite of the Next.js `frontend/`; the two frontends coexist.
- No automated translation of research prose beyond the UI chrome unless scoped later.

## Decisions

- **BFF adapter in SvelteKit.** Route handlers under `src/routes/api/` (or `src/lib/server/rsal.ts` helpers) proxy to RSAL using `RSAL_API_URL` (server-side env). They translate RSAL view models to the Svelte view models. Browser never calls RSAL directly. Alternative: call RSAL from the browser — rejected (CORS, secret URL exposure, no shaping).
- **Data mapping.** Observations become scenes (multitemporal scene foundation) filtered by sensor; water/vegetation area series come from scene metadata/aggregations; samples come from RSAL query batches persisted client-side; models/metrics come from training runs + `/metrics`. Where RSAL lacks a field, the UI degrades gracefully (empty state) rather than fabricating values.
- **Raster rendering stays client-side.** geotiff.js (or existing Leaflet image overlay) fetches original bytes via the adapter file endpoint; band modes RGB/false-color/NDVI/custom retained; pixel-space fallback for non-georeferenced rasters (Leaflet CRS.Simple).
- **Review queue is client state.** RSAL `/query` is stateless; the batch lives in a persisted Svelte store (localStorage, per project). Skips and drafts local; submitted labels real RSAL labels. Keyboard shortcuts (1-9, Enter submit, S skip, arrows) retained.
- **i18n architecture.** A lightweight Svelte store (`locale`) with two dictionaries (`en`, `fa`) and a `t(key)` helper; no heavy i18n dependency to keep the example light. RTL applied via `dir="rtl"` on `<html>` when locale is `fa`. Dates/numbers via `Intl` with the active locale. Preference persisted in localStorage and synced to a cookie for SSR. Alternative: `svelte-i18n` — considered but adds bundle weight; revisit if catalogs grow.
- **Styling for RTL.** Tailwind logical properties (`ms-`, `me-`, `ps-`, `pe-`, `text-start/end`) instead of physical left/right; avoid hardcoded `ml-`/`mr-` in layout. Map controls mirrored where needed.
- **Coexistence.** Example app gets its own port (5173 dev / preview) and optional compose profile; not added to default compose services to avoid breaking existing frontend.
- **Verification.** Typecheck (`svelte-check`, `tsc --noEmit`) + production build; live smoke script hitting adapter endpoints; bilingual smoke (switch locale, check `dir`, sample translated strings).

## Risks / Trade-offs

- [Mock-to-real impedance mismatch] The research views assume rich derived series (water area over time) that RSAL may not directly expose → Mitigation: derive from scenes where possible, otherwise show empty/limited state and document; never fabricate.
- [Client-persisted queue per browser] same as TerraLab trade-off → acceptable for single-analyst MVP.
- [i18n coverage drift] new strings may ship untranslated → Mitigation: fall back to English key and a lint check that all keys exist in both dictionaries.
- [RTL layout regressions] physical Tailwind classes → Mitigation: migrate to logical properties and add RTL visual smoke.
- [Two frontends to maintain] → Mitigation: example is optional and clearly scoped; backend contracts unchanged.

## Migration Plan

1. Move folder (done) and update README paths.
2. Add RSAL adapter layer in the example app (env, server helpers, route handlers).
3. Replace mock data imports with adapter calls view by view (overview → geospatial → temporal → learning → arena → evaluation).
4. Add client-persisted review store and keyboard shortcuts (port from existing mock behavior).
5. Add i18n store + dictionaries + RTL + persisted preference; migrate UI strings.
6. Update docs (example README, root README, optional compose profile).
7. Verify typecheck/build/smoke/bilingual.

## Open Questions

- Should the example app be added to default `docker-compose.yml` or an `examples` profile? Proposed: optional profile to keep default footprint small. (Deferrable; does not change specs.)
- Which RSAL scene fields provide the temporal water-area series? To be confirmed during implementation; UI degrades gracefully if unavailable.
