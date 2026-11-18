# Tasks

## 1. Relocation and baseline

- [x] 1.1 Move `wbalc-geospatial-research-interface/` to `examples/wbalc-geospatial-research-interface/` and verify `package.json` resolves and `npm run check` runs (no new errors)
- [x] 1.2 Update example README paths and add a "Runs against WBALC (RSAL)" section listing `RSAL_API_URL`, and verify the documented dev command starts
- [x] 1.3 Add example app to root README (optional frontend example) and verify links resolve

## 2. RSAL adapter (BFF)

- [x] 2.1 Add server-side RSAL client helper (`src/lib/server/rsal.ts`) reading `RSAL_API_URL` and verify a health probe returns 200
- [x] 2.2 Add route handlers for projects (list/get) and verify JSON matches app view models
- [x] 2.3 Add route handlers for datasets (list/get/file/delete) and verify file bytes stream correctly
- [x] 2.4 Add route handlers for labels (list/submit/correct/delete) and verify round-trip
- [x] 2.5 Add route handlers for query (batch) and training/metrics, and verify responses proxy correctly
- [x] 2.6 Add route handlers for scenes (list/get) and verify metadata reaches temporal view

## 3. Replace mock data with live data (view by view)

- [x] 3.1 Remove static research datasets from `src/lib/data/research.ts` and wire Overview to adapter; verify no mock arrays remain
- [x] 3.2 Wire Geospatial Workspace to real datasets/rasters; verify map renders from RSAL file bytes
- [x] 3.3 Wire Temporal Analysis to real scenes; verify date pickers and metadata
- [x] 3.4 Wire Active Learning to real query batches + client-persisted store; verify keyboard shortcuts
- [x] 3.5 Wire Model Arena to real training/metrics; verify confusion matrix
- [x] 3.6 Wire Results & Evaluation to real metrics; verify filters and CSV export

## 4. Client-persisted review state

- [x] 4.1 Implement per-project persisted review store (localStorage) and verify restore after reload
- [x] 4.2 Implement skip/draft handling and verify counts update
- [x] 4.3 Implement label correction and deletion UI and verify RSAL round-trip

## 5. Internationalization (Persian/English)

- [x] 5.1 Add locale store with `en`/`fa` dictionaries and `t()` helper; verify switching updates strings
- [x] 5.2 Apply `dir`/`lang` on root and migrate layout to logical properties; verify RTL smoke
- [x] 5.3 Add locale-aware date/number formatting and verify sample outputs
- [x] 5.4 Persist locale preference and restore before first paint; verify reload
- [x] 5.5 Add translation completeness check and verify it passes for both dictionaries
- [x] 5.6 Translate all UI chrome strings (en + fa) and verify no missing keys

## 6. Verification and packaging

- [x] 6.1 Typecheck (`svelte-check`, `tsc --noEmit`) and production build; verify green
- [x] 6.2 Live end-to-end smoke through adapter against real RSAL; verify create→upload→query→label→train→metrics
- [x] 6.3 Bilingual smoke (locale switch, dir, sample strings) and verify
- [x] 6.4 Optional compose profile for example app and verify `docker compose` config validates
