## 1. Audit and specification
- [x] 1.1 Audit current WBALC inference, raster, training, Dataset/Scene, UI request paths and synthetic tests; record existing behavior and gaps in `audit.md`.
- [x] 1.2 Write proposal, design decisions, capability requirements and the complete task plan before implementation.
- [x] 1.3 Resolve legacy-checkpoint behavior (explicit recorded override only) and UI Dataset selection (visible selection always submitted) before changing runtime behavior.

## 2. Input identity and feature schema
- [ ] 2.1 Specify and implement explicit reference Dataset selection for pixel inference; validate project ownership and return Dataset/run/resolution provenance.
- [ ] 2.2 Add ordered band/schema identity to model and prepared Dataset inputs using the smallest safe additive change; validate all Datasets before combining training samples and do not infer missing sensor semantics.
- [ ] 2.3 Add clear mismatch/unknown-schema handling; require a visible, recorded user override where the approved design allows unverified compatibility.
- [ ] 2.4 Add idempotent additive migration only if persistence changes require it; test against fresh and existing schemas without rebuilding or rewriting source files.

## 3. Study-area pixel mask
- [ ] 3.1 Transform the project vector geometry into the selected raster CRS without changing the raster; fail clearly for absent CRS or failed coordinate operation.
- [ ] 3.2 Combine pixel-center study-area inclusion with all-band source validity for pixel predictions.
- [ ] 3.3 Propagate the combined mask consistently through hard, probability, uncertainty, API/map responses and all pixel exports; record whether the mask was applied.
- [ ] 3.4 Preserve and test existing patch-mode behavior; do not claim study-area masking for patch products unless implemented and verified.

## 4. Resolution selection and resource bounds
- [ ] 4.1 Make UI/API pixel-versus-patch selection and omitted-value behavior consistent while preserving legacy patch checkpoints and request compatibility.
- [ ] 4.2 Audit every full-raster allocation and enforce configured limits before allocation; implement streaming only if all affected response/export paths can preserve parity.
- [ ] 4.3 Document actual memory behavior, limits, resolution semantics and non-goals; make failure messages actionable.

## 5. Synthetic regression coverage
- [ ] 5.1 Add synthetic 101×73 GeoTIFF tests with known class boundaries and exact values; keep existing 7×11 rotated-affine/NoData tests.
- [ ] 5.2 Test explicit Dataset selection, foreign/missing Dataset rejection, same-count reordered/unknown band schemas and legacy checkpoints.
- [ ] 5.3 Test study polygons inside/outside, pixel-center boundaries, projected/geographic CRS conversion, missing CRS, invalid geometry, and conjunction with source masks.
- [ ] 5.4 Test pixel/patch resolution compatibility, partial windows, output nodata for all products, source-byte immutability, and reopened output grid parity.
- [ ] 5.5 Add focused frontend/API contract tests for selected Dataset/resolution and provenance display.

## 6. Verification and acceptance evidence
- [ ] 6.1 Run focused backend tests and complete backend suite; record exact commands/results.
- [ ] 6.2 Run frontend tests, typecheck/lint and production build; record exact commands/results.
- [ ] 6.3 Complete a manual QGIS overlay check using synthetic/reference and exported rasters; record software/version, test fixture, layers and observations. Do not mark complete without human execution.
- [ ] 6.4 Review diff for immutable-source guarantees, no implicit raster alignment, accurate claims and absence of unrelated refactors.
