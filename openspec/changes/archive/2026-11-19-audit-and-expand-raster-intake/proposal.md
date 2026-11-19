## Why

The research workspace assumed a fixed water taxonomy and one already-assembled GeoTIFF. Users with dated Sentinel folders had to prepare and document every stack outside the app. The audit also found that sampling could score a same-count but differently ordered raster, and the map could retain stale pixels after changing inputs.

## What Changes

- Default new workspace projects to editable `water` and `non_water` classes. Add class rows at creation or append classes to existing projects without rewriting old runs.
- Inspect multiband GeoTIFF headers and request one name per band. Stage separate single-band files or provisional dated folders in a review dialog and import independently per acquisition.
- Display named source bands and add/remove per-raster normalized-difference previews. Use declared band identity for color composites and hide unsupported presets.
- Reject incompatible model-scored queries, retain recorded checkpoint class order, and prevent stale map responses crossing datasets.

## Capabilities

### New Capabilities
- `raster-intake`: Reviewed raster input and named, dataset-scoped display layers.

## Impact

SvelteKit workspace, existing project/query API semantics, new stack ingestion API, local visual QA and regression tests. Existing files and checkpoints are not rewritten.
