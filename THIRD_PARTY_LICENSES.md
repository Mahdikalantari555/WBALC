# Third-party dependency license inventory

Inventory re-verified **2026-11-18** against the committed frontend lockfile
(`frontend/package-lock.json`, 843 package records) and a clean Python
environment resolved from `requirements.lock.txt`. This is an automated metadata
inventory plus dependency-path tracing, not legal advice. It does not replace
shipping each dependency's license/notice text with a distributed build.

## Python

`requirements.lock.txt` (the Docker image's pinned runtime set) resolves to 49
distributions. Metadata is predominantly MIT, BSD-2/3-Clause, Apache-2.0,
PSF-2.0 and MPL-2.0 (rasterio/GDAL bindings, numpy, scikit-learn, LightGBM,
FastAPI/pydantic/SQLAlchemy stack). No GPL/AGPL/LGPL package is reported for the
runtime set. The development environment adds test/lint tooling only.

Security: `pip-audit -r requirements.lock.txt` and `-r requirements-dev.txt`
both report **no known vulnerabilities** at this date. The only findings in the
local development virtualenv are for `pip`/`setuptools` themselves (packaging
tooling, not runtime application dependencies).

## Frontend

`package-lock.json` (843 records, including transitive and platform-optional
packages). License distribution: 612 MIT, 70 ISC, 60 Apache-2.0, 37 BSD-3-Clause,
13 MPL-2.0, 10 BSD-2-Clause, 14 LGPL-3.0-or-later-labelled entries (all
`@img/sharp*` platform binaries), plus the non-standard entries below.

### Items that need attention before redistribution

| Package(s) | License metadata | Dependency path | Note |
|---|---|---|---|
| `@img/sharp-libvips-*` (9 platform packages, 1.3.4) and `@img/sharp-wasm32`, `@img/sharp-win32-*` (0.35.5) | LGPL-3.0-or-later (some also Apache-2.0/MIT) | `next` → optional `sharp` | LGPL native image binaries. If the Docker image or a build ships them, LGPL source/relinking obligations apply. The Next.js server may install `sharp` as an optional dependency; verify the produced image contents. |
| `@arcgis/core` 4.34.8 | "SEE LICENSE IN copyright.txt" (Esri custom terms) | `deck.gl` → `@deck.gl/arcgis` → `@arcgis/core` | Pulled in by the `deck.gl` meta-package, not by application code. Tutorial/attribution terms apply if distributed. |
| `@amcharts/amcharts5` 5.14.4 | "SEE LICENSE IN LICENSE" (amCharts terms) | `deck.gl` → `@deck.gl/arcgis` → `@arcgis/core` → `@amcharts/amcharts5` | Not a direct dependency and not imported by the workspace; it is a transitive dependency of the ArcGIS integration. Confirm whether it is in the built bundle (tree-shaking) and whether a commercial license is needed. |
| `react-leaflet` 5.0.0, `@react-leaflet/core` 3.0.0 | Hippocratic-2.1 | direct dependency | Ethical/source-available terms; review compatibility with the intended distribution policy. |
| `caniuse-lite` 1.0.30001823, `cartocolor` 5.0.2 | CC-BY-4.0 | transitive (`browserslist`, `d3-scale-chromatic`) | Attribution required where the data is redistributed. |
| `colorbrewer` 1.5.6 | Apache-Style (registry metadata) | transitive (`d3-scale-chromatic`) | Verify the actual license text before redistribution. |
| `jszip` 3.10.2 | (MIT OR GPL-3.0-or-later) | transitive | Choose and preserve the MIT option where permitted. |
| `sax` 1.6.1 | BlueOak-1.0.0 | transitive | Retain notice. |
| `robust-predicates` 3.0.3 | Unlicense | transitive (`delaunator`) | Public-domain style; jurisdiction review if redistributing. |

Charts in the workspace use `recharts` (MIT); `amCharts` is **not** a direct
dependency and is not referenced by application code. Earlier revisions of this
document implied otherwise; that is corrected here.

## Security advisories (npm)

`npm audit` on the current lockfile:

- **Baseline (before this change):** 29 advisories — 10 moderate, 19 high.
- **After this change:** 28 advisories — 10 moderate, 18 high. The removed
  finding is `postcss` (direct devDependency) bumped 8.5.8 → 8.5.33 (patch).

Remaining findings, triaged by role:

1. **`deck.gl` 9.4.1 meta-package** (direct, runtime): `@loaders.gl/{3d-tiles,
   gltf, textures, zip, compression}`, `@luma.gl/gltf`, `image-size`,
   `texture-compressor`, `fflate`. These are the 3D-tiles/glTF/compression
   loaders, unused by this workspace's `ScatterplotLayer`/`GeoJsonLayer` usage.
   `npm audit` only offers `deck.gl@9.1.0` (a downgrade) as a "fix"; the real fix
   is an upstream release that bumps `@loaders.gl`. Blocked: no compatible fix.
2. **`eslint-config-next` 16.4.5** (direct dev) → `@next/eslint-plugin-next`,
   `typescript-eslint` chain → `fast-glob`/`micromatch`/`picomatch`/`fdir`/
   `tinyglobby`/`minimatch`. Development-time lint tooling only; `npm audit`
   proposes `eslint-config-next@14.2.35` (a major downgrade). Blocked.
3. **`postcss`** — fixed (above). `@tailwindcss/postcss` uses it at build time.

No critical advisories. No runtime finding is reachable from the server (the
frontend is a static/server-rendered Next app; the vulnerable loaders are not
imported). Severity counts reported by `npm audit` are aggregate and can shift
when the advisory database re-rates a transitive chain without any version
change; treat the per-advisory list, not the count, as the source of truth.

## Repository license scope

The root MIT `LICENSE` applies to repository-authored code only. It does not
relicense dependencies, raster data, or other third-party assets. Before
publishing a fork or container image, generate a version-specific SBOM and ship
the required third-party notices, with particular review of the LGPL
`sharp`/libvips binaries and the Esri/amCharts/Hippocratic terms above. An
automated metadata inventory is not a redistribution clearance.
