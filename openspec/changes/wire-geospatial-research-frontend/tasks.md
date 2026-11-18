# Tasks

## 1. Relocation and baseline

- [ ] 1.1 Move `wbalc-geospatial-research-interface/` to `examples/wbalc-geospatial-research-interface/` and verify `package.json` resolves and `npm run check` runs (no new errors)
- [ ] 1.2 Update example README paths and add a "Runs against WBALC (RSAL)" section listing `RSAL_API_URL`, and verify the documented dev command starts
- [ ] 1.3 Add example app to root README (optional frontend example) and verify links resolve

## 2. RSAL adapter (BFF)

- [ ] 2.1 Add server-side RSAL client helper (`src/lib/server/rsal.ts`) reading `RSAL_API_URL` and verify a health probe returns 200
- [ ] 2.2 Add route handlers for projects (list/get) and verify JSON matches app view models
- [ ] 2.3 Add route handlers for datasets (list/get/file/delete) and verify file bytes stream correctly
- [ ] 2.4 Add route handlers for labels (list/submit/correct/delete) and verify round-trip
- [ ] 2.5 Add route handlers for query (batch) and training/metrics, and verify responses proxy correctly
- [ ] 2.6 Add route handlers for scenes (list/get) and verify metadata reaches temporal view

## 3. Replace mock data with live data (view by view)

- [ ] 3.1 Remove static research datasets from `src/lib/data/research.ts` and wire Overview to adapter; verify no mock arrays remain
- [ ] 3.2 Wire Geospatial Workspace to real datasets/rasters; verify map renders from RSAL file bytes
- [ ] 3.3 Wire Temporal Analysis to real scenes; verify date pickers and metadata
- [ ] 3.4 Wire Active Learning to real query batches + client-persisted store; verify keyboard shortcuts
- [ ] 3.5 Wire Model Arena to real training/metrics; verify confusion matrix
- [ ] 3.6 Wire Results & Evaluation to real metrics; verify filters and CSV export

## 4. Client-persisted review state

- [ ] 4.1 Implement per-project persisted review store (localStorage) and verify restore after reload
- [ ] 4.2 Implement skip/draft handling and verify counts update
- [ ] 4.3 Implement label correction and deletion UI and verify RSAL round-trip

## 5. Internationalization (Persian/English)

- [ ] 5.1 Add locale store with `en`/`fa` dictionaries and `t()` helper; verify switching updates strings
- [ ] 5.2 Apply `dir`/`lang` on root and migrate layout to logical properties; verify RTL smoke
- [ ] 5.3 Add locale-aware date/number formatting and verify sample outputs
- [ ] 5.4 Persist locale preference and restore before first paint; verify reload
- [ ] 5.5 Add translation completeness check and verify it passes for both dictionaries
- [ ] 5.6 Translate all UI chrome strings (en + fa) and verify no missing keys

## 6. Verification and packaging

- [ ] 6.1 Typecheck (`svelte-check`, `tsc --noEmit`) and production build; verify green
- [ ] 6.2 Live end-to-end smoke through adapter against real RSAL; verify create→upload→query→label→train→metrics
- [ ] 6.3 Bilingual smoke (locale switch, dir, sample strings) and verify
- [ ] 6.4 Optional compose profile for example app and verify `docker compose` config validates
