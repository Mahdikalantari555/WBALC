# WBALC | Zarivar Lake research workspace

WBALC (Water Body Active Learning Classification) is a frontend-only SvelteKit prototype for exploring how Sentinel-1 SAR and Sentinel-2 optical observations could support open-water and aquatic-vegetation mapping. The app opens on the Geospatial Workspace.

## Run locally

Use Node.js 20.19+ or 22.12+ and npm.

```sh
npm ci
npm run dev:kit
```

Open the local URL printed by Vite. For a static production build, run `npm run build:kit`, then `npm run preview:kit`. The static output is `build/`. No application server or API keys are required. After installing dependencies, the app uses only local assets, including imagery and fonts.

The original starter entry remains available through `npm run dev`, `npm run build`, and `npm run preview`. Its small React bridge in `src/App.tsx` mounts the same Svelte workspace. The SvelteKit entry at `src/routes/+page.svelte` renders it directly and does not ship React. Use `npm run check` for Svelte and TypeScript diagnostics.

## Research views

| View | What to try |
| --- | --- |
| Overview | Review the project status, shared water-area series, latest observation, model summary, and activity. Filter the chart by sensor or select an observation. |
| Geospatial Workspace | Pan or zoom the offline Leaflet map. Switch between the satellite-style illustration and terrain schematic, toggle vector layers, change opacity, inspect a sample or classification, and export displayed vector layers as GeoJSON. |
| Temporal Analysis | Filter 12 observations by sensor, select dates from the chart or date pickers, swap the comparison dates, and inspect acquisition metadata and the schematic water gain/loss map. |
| Active Learning | Filter the local queue by review status, uncertainty, and predicted class. Compare predicted overlays with the illustration, label samples, and verify that counts update. Labels persist in browser storage. |
| Model Arena | Compare Sentinel Fusion RF, Optical U-Net, and SAR Threshold across five metrics and inference time. Switch detailed metrics between the two selected models and inspect their side-by-side footprints and configuration. |
| Results & Evaluation | Filter by model and reference class, inspect confusion counts or row percentages, select example error sites, and download simulated CSV and GeoJSON results. |

The project menu opens the project overview. The toolbar date applies across the workspace, and notification items link to their relevant views. Use the local profile menu to reset demo reviews. View URLs are shareable hash links, for example `/#/temporal`.

## Source layout

| Path | Responsibility |
| --- | --- |
| `src/lib/Workspace.svelte` | Shared navigation, toolbar, local preferences, and research view shell |
| `src/lib/state.svelte.ts` | Shared observation, map, model, and review state |
| `src/lib/pages/` | Six research views |
| `src/lib/components/` | Leaflet map, map previews, chart, selectors, and evaluation tables |
| `src/lib/data/` | Typed mock dataset, illustrative map geometry, metric calculations, and browser exports |
| `public/maps/` | Bundled satellite-style illustration and vector terrain fallback |

## Scope and limitations

- One study area and one image illustration are bundled. Dates and sensors use schematic footprints and a grayscale SAR-style treatment, not distinct scenes or measured radar backscatter. The coordinates, areas, map scale, and GeoJSON geometry are indicative and are not suitable for scientific or navigation use.
- Class predictions, validation counts, uncertainty, and inference times are simulated. Precision, recall, F1, and IoU are derived from the fixed mock confusion counts. Local labeling does not change these benchmark results or trigger retraining.
- The project reviewed total includes 124 illustrative archive reviews; only the 12 samples in the prototype queue can be inspected or edited. Edits are browser-local and are not shared across users or devices.
- No backend, authentication, database, satellite acquisition, or model execution is implemented.