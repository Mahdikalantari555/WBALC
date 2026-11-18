## Context

A WBALC project currently has both a generic `classes` list and a separate `classification_config.internal_classes`; new projects commonly align, but arbitrary classes remain possible and downstream training uses `Project.classes`. The binary choice is persisted but not applied. This change closes the semantic gap without altering legacy project data.

## Decisions
- Canonical internal outputs for WBALC projects are ordered `open_water`, `emergent_vegetation`, `land`. Existing non-WBALC/custom projects keep their class list and old behavior until explicitly configured/migrated.
- Persist a versioned label crosswalk from submitted label names to canonical class IDs. Preserve original submitted label text for audit; resolve model targets through the crosswalk. Unknown or ambiguous values fail validation. A `reed` label maps to `emergent_vegetation` only if explicitly configured by the project; do not state that emergent vegetation is exclusively reeds.
- The three-class product is the source of truth. Binary interpretation creates a derived categorical raster with documented class mapping and NoData propagation; it never overwrites/collapses the three-class product. Probability recoding sums the relevant internal class probabilities and preserves NoData.
- Define binary mappings exactly: `water_vs_non_water` => open_water + emergent_vegetation are water; `open_water_vs_other` => only open_water is water. Record a machine-readable mapping, source run, config version and grid in exports.
- If the model has not learned one or more canonical classes, report absent classes and do not synthesize probabilities. An optional binary product can be generated only if the classes needed by its mapping are represented in model output; otherwise return a clear not-available state.
- Keep color/display mappings keyed by stable class IDs; no class meaning inferred from palette colors.
- UI labels explain the distinction between internal taxonomy and derived binary interpretation.

## Migration and compatibility
Existing Project.classes and Label rows are not rewritten. Add config columns/JSON fields only through a numbered idempotent additive migration if needed. Checkpoint readers preserve old class lists and class ordering. Explicit project config changes apply to future runs; historical run/export semantics remain fixed by their recorded config.

## Verification
Synthetic label/config tests and tiny GeoTIFF classification fixtures validate crosswalks, internal class order, binary recoding, probability summation, nodata, region grids, legacy behavior and missing-class handling. No real satellite data or internet.

## Risks
Taxonomic labels are domain judgments; software must expose, not invent, that mapping. Binary products can hide mixed emergent vegetation/open-water meanings; always retain and link the three-class source output. Class order changes are breaking for checkpoints and must be rejected unless a new training run is produced.
