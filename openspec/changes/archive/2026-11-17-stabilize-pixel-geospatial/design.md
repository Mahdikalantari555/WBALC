## Design

### Compatibility contract
`resolution` defaults to `patch`, preserving current train/predict semantics. The new `pixel` setting is persisted in checkpoint metadata and must match at inference. Pixel mode uses per-pixel band values in row-major order, no spatial interpolation, a strict per-pixel all-band mask, and an exact source affine. Patch context is not substituted for pixel predictions.

### Labels and pixel targets
Point labels map by inverse affine into the containing pixel (floor of pixel coordinates); outside points fail at submission. Polygon labels affect pixel centers inside a valid polygon; patches are not the pixel target. Legacy label sets may lack an unambiguous per-pixel target; when a pixel-mode training selection cannot resolve sufficient targets, training returns a clear conflict instead of inventing labels.

### Raster grids and output
Source-grid writers receive an explicit reference profile and validate dimensions, CRS, transform, and bounds before writing and after reopening. Class rasters are integer categorical values with a dedicated NoData sentinel. No resize or bilinear/cubic resampling is permitted. Window tiling must include the final partial window and mask invalid pixels.

### Evaluation
Spatial mode groups samples into spatial blocks and holds out whole blocks, stratifying where possible. If the data cannot yield a valid independent split, report `evaluation=insufficient` with a reason rather than training-set performance. Existing random holdout remains available and is labeled random holdout. The deployed estimator refits on all usable labeled samples after evaluation.

### Limits
The first implementation keeps the current synchronous service architecture and may still materialize arrays for some code paths. It must enforce the existing memory guard and document this; true out-of-core model inference is follow-up work unless verified here. No claim of improved accuracy is made.
