# Roadmap status — Phases 0–5 applied

Branch: `arena/a4a6bd6b-wbalc`
Last updated: 2026-11-19 (sandbox clock). Synthetic data only.

## Commits

| Phase | Change | Commit |
| --- | --- | --- |
| 0 | `harden-pixel-classification-contract` | `26fc9e7` |
| 1 | `phase-1-water-classification` | `85e9440` |
| 2 | `phase-2-active-learning-provenance` | `addb6dc` |
| 3 | `phase-3-experiment-lineage` | `9d73a93` |
| 4 | `phase-4-temporal-water-mapping` | `8f4f834` |
| 5 | `phase-5-research-evaluation` | `36dde45` |
| — | integrated end-to-end acceptance + report-digest fix | this commit |

Each phase has its own `verification.md` with the commands that were actually run, the
results, and a "Not verified / limits" section.

## Final gate (this commit)

```
.venv/bin/python -m pytest -p no:warnings          # 336 passed in 114.93s
cd examples/wbalc-geospatial-research-interface
npx svelte-check --tsconfig ./tsconfig.json        # 0 errors, 0 warnings
npx vitest run                                     # 5 files, 78 tests passed
node scripts/check-i18n.mjs                        # 547 keys
npx vite build                                     # adapter-node
.venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5176
```

## What is complete

- **Software**: all six phases are implemented, tested and wired to the UI. `tests/test_end_to_end_workflow.py`
  walks one synthetic scene from ingest through query/labels, training, inference, lineage, temporal
  analysis and fusion to a held-out evaluation and a regenerable report bundle.
- **Guards against dishonest results**: unidentified band schemas are refused, grids are never silently
  aligned, splits the data cannot support are stored as `insufficient`, undefined class metrics are `null`
  with a reason, area error needs operator-supplied truth, ratios never fall back to a default denominator,
  and comparisons say when they are not paired.
- **Migration**: additive versions 1…10, verified against a legacy RSAL-style database; project deletion
  now cascades Phase 3–5 records instead of orphaning them.

## Design system (applied after Phase 5)

The research-workspace frontend now has a shadcn-structured primitive layer
(`components.json`, `$lib/utils` with `cn()`, `src/lib/components/ui/<name>/`),
and the drift it was meant to prevent is checked rather than trusted:

| Before | After |
| --- | --- |
| 79 hex colours in `index.css` + 150 hard-coded across components | one oklch token layer; **0** hex values in `.svelte` files |
| `.button` / `.button.primary` / `.button.quiet` / `.button.small` at 33 call sites | `Button` with `variant`/`size` |
| `inline-error` blocks hand-rolled per page | `Alert` (one shape, one role, one icon) |
| 9 labels below 10px | nothing below 10px, enforced by a test |
| placeholder-only inputs with no accessible name | `aria-label`/`id` + `for`, enforced by a test |
| dead `AsyncState.svelte` (0 importers) | removed |
| `--destructive` text at 4.42:1 on cards (under AA) | 4.98:1; the whole text/surface matrix is asserted |

`src/lib/components/ui/design-system.test.ts` runs 27 assertions including a
computed WCAG contrast table (`contrast.ts`), so the palette cannot regress
silently. **No light theme ships**: the map/raster chrome still assumes a dark
surface, and a half-themed app is worse than a dark-only one. That is recorded as
an explicit non-claim, not an oversight.

## What is NOT complete — read this before quoting any number

1. **No real satellite imagery and no independent reference data exist in this repository.** Every metric
   in this repo comes from synthetic fixtures. `GET /projects/{id}/research/status` therefore reports
   `scientific_validity: "not established"`, and that is the correct answer, not a placeholder to be
   removed later.
2. **Manual GIS overlay check (task 3.5) has not been performed.** Automated tests verify bytes, grids,
   checksums and geometry; they do not verify that a map looks right in QGIS/ArcGIS. This is the one
   roadmap acceptance item still open, and it needs a human with a GIS application.
3. **No Active-Learning-vs-random experiment has been run on real data.** The machinery (seeded random
   baseline, matched plans, pairing verdict) exists and is tested; no learning-curve claim is made.
4. **Public/benchmark comparison is out of scope by design.** There is no bundled external dataset, no
   comparison with published water-mapping accuracies, and no universal accuracy threshold.

Reporting software completion and scientific validity as the same thing would be the exact failure mode
Phase 5 was built to prevent.
