## ADDED Requirements
### Requirement: explicit source-pixel supervised classification
The system SHALL support RF and LightGBM models trained with per-pixel spectral feature vectors and SHALL predict each valid source pixel directly without resizing a patch map. The system SHALL preserve legacy patch mode when resolution is omitted. A checkpoint SHALL identify its resolution/feature contract.

#### Scenario: pixel model output
- GIVEN a trained pixel-resolution checkpoint and a reference raster
- WHEN inference is run
- THEN the hard prediction grid has the region's exact width and height and uses the pixel affine
- AND invalid input pixels remain NoData
- AND categorical values are not interpolated.

#### Scenario: pixel label identity
- GIVEN point labels for different pixels within one legacy patch
- WHEN labels declare pixel sample resolution
- THEN they remain distinct training targets rather than overwriting one another.
