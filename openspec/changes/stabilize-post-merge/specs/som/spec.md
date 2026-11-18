## ADDED Requirements

### Requirement: SOM excludes invalid observations
The SOM explorer and the unsupervised classifier SHALL exclude observations without
valid pixels from fitting, from hit counts, from representative samples and from
returned sample ids; pixel mode SHALL require all bands to be valid.

#### Scenario: Nodata collar in the explorer
- **WHEN** a quarter of a scene is nodata
- **THEN** `valid_patches` reflects only valid patches, `nodata_patches` reflects the rest, and no cell lists a sample id from a nodata patch

#### Scenario: Partially masked pixel
- **WHEN** a pixel is nodata in one band and SOM classification runs in pixel mode
- **THEN** that pixel is nodata in the output, not imputed into a cluster

### Requirement: SOM model overlays require a compatible checkpoint
The SOM explorer SHALL annotate cells with supervised predictions only when the
checkpoint was trained on patch features with the dataset's band count; otherwise it
SHALL omit the annotations and say why.

#### Scenario: Pixel checkpoint present
- **WHEN** the latest run was trained at pixel resolution
- **THEN** the explorer returns `model_iteration: null` with an explanatory note instead of failing

### Requirement: SOM GeoTIFFs use the source grid
SOM classification exports SHALL be validated against the source window in both
resolutions, with nodata for unclassified cells.

#### Scenario: Patch-mode SOM export
- **WHEN** patch-mode SOM classification is exported
- **THEN** the raster has the region's dimensions and affine, and cells are painted over their true pixel windows
