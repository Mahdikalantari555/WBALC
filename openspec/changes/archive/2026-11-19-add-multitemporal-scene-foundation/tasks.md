## 1. Baseline and specification
- [x] 1.1 Audit WBALC and the linked RSAL repository; record reusable architecture, incompatibilities, and risks.
- [x] 1.2 Establish OpenSpec configuration, proposal, design, capability requirements, and this complete implementation task plan before coding.
- [x] 1.3 Import the inspected RSAL baseline without its `.git` directory; preserve its app, frontend conventions, and tests.

## 2. Domain and persistence
- [x] 2.1 Add project study-area fields and validated three-class/binary classification configuration with backward-compatible defaults.
- [x] 2.2 Add the Scene ORM model with independent acquisition, sensor-specific, raster-grid, band, NoData/mask, source, and timestamps metadata.
- [x] 2.3 Add explicit numbered, idempotent additive database migration(s); preserve inherited project/dataset data.
- [x] 2.4 Add typed request/response schemas and sensor/acquisition metadata validation.

## 3. Raster ingestion and grid integrity
- [x] 3.1 Extend shared raster metadata inspection to report all band names/descriptions/dtypes, per-band nodata/mask flags, resolution, affine, dimensions, CRS and bounds.
- [x] 3.2 Implement upload validation and immutable source staging/registration with failure cleanup and configured upload limits.
- [x] 3.3 Implement structured native-grid comparison that independently identifies CRS, pixel size, affine origin/rotation, dimensions, and extent differences; document categorical/continuous resampling policy concepts without performing alignment.

## 4. API
- [x] 4.1 Extend project create/read/list schemas and routes for study geometry/CRS and classification configuration.
- [x] 4.2 Add project-scoped scene upload, temporally ordered list, detailed get, spatial metadata get, and isolated delete endpoints.
- [x] 4.3 Return complete scene metadata and clear 404/413/422 errors; retain existing dataset APIs and processing behavior.

## 5. Frontend
- [x] 5.1 Add project study metadata/classification inputs while preserving existing project selection and design patterns.
- [x] 5.2 Add scene upload controls for sensor and acquisition/product metadata.
- [x] 5.3 Add temporally ordered scene list/details with acquisition date, sensor, bands, CRS, resolution, dimensions, and useful validation errors.

## 6. Automated verification
- [x] 6.1 Add synthetic GeoTIFF tests for scene metadata, Sentinel-1/2, optional fields, invalid files, NoData, masks, and source immutability.
- [x] 6.2 Add tests for multiple scenes, duplicate/missing dates, CRS/affine/pixel-size/dimension/extent differences, and grid comparison diagnostics.
- [x] 6.3 Add tests for isolated deletion, full API response semantics, persistence, and migration against both fresh and pre-existing RSAL-style schemas.
- [x] 6.4 Run backend and frontend tests, type checking, and build where dependencies/environment allow; report only actual results.
