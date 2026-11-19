## ADDED Requirements

### Requirement: Pixel mode classifies individual source pixels
In pixel mode every valid source pixel SHALL receive an independently computed
prediction from its own band values, with no upsampling and no interpolation.

#### Scenario: One prediction per pixel
- **WHEN** a pixel-resolution model is applied to a 64×64 scene
- **THEN** `hard_map`, `probability_map`, `uncertainty_map` and `valid_map` are all 64×64 and the export is 64×64 on the source affine

#### Scenario: Partially masked pixel
- **WHEN** a pixel is nodata in any band
- **THEN** it is invalid in pixel mode and receives no class

### Requirement: Patch mode output is labelled as patch cells
Patch-mode rasters SHALL contain one value per patch cell replicated over that
cell's pixel window, SHALL record `resolution=patch-cells`, and SHALL NOT be
described as pixel-level classification.

#### Scenario: Patch export metadata
- **WHEN** a patch-mode export is downloaded
- **THEN** its tags contain `resolution=patch-cells`, `grid` (per-cell windows) and the patch size/stride, and the API reports `resolution: "patch"`

#### Scenario: API distinguishes the modes
- **WHEN** a client reads `POST /predict` or `GET /predict/map`
- **THEN** the response states the classification resolution it used
