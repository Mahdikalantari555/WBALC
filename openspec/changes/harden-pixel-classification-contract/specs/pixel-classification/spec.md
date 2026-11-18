## ADDED Requirements

### Requirement: Explicit reference raster for pixel inference
The system MUST identify the exact project-owned Dataset used as the reference raster for every pixel inference and export. A pixel inference MUST NOT silently select a different or most-recent Dataset without exposing that choice in the request/response and resulting export provenance.

#### Scenario: Explicit reference Dataset selected
- **WHEN** a user requests pixel inference for a Dataset belonging to the project
- **THEN** inference uses that Dataset's own band stack, dimensions, CRS, affine transform and validity masks
- **AND** the response and exports identify the Dataset and training run used

#### Scenario: Dataset does not belong to the project
- **WHEN** a request names a Dataset outside the project or a nonexistent Dataset
- **THEN** the request fails before opening raster data
- **AND** no export is published

### Requirement: Resolution is explicit and compatible
The system MUST preserve the checkpoint's training resolution as the inference contract and MUST clearly distinguish independent source-pixel predictions from patch-cell predictions. New UI prediction/training requests MUST expose the selected resolution rather than depending on a conflicting implicit default.

#### Scenario: Pixel checkpoint inference
- **WHEN** a pixel-trained checkpoint is used
- **THEN** each valid output cell represents exactly one source pixel
- **AND** output dimensions and transform correspond to the selected source region

#### Scenario: Patch checkpoint inference
- **WHEN** a patch-trained checkpoint is used
- **THEN** the result is identified as patch-cell resolution and is not described as independent per-pixel classification

#### Scenario: Resolution mismatch
- **WHEN** a request attempts to override the checkpoint with an incompatible resolution
- **THEN** the system rejects it with a clear error rather than silently relabeling output

### Requirement: Study area constrains pixel predictions when configured
When a project has a study-area geometry, pixel prediction validity MUST be the conjunction of source all-band validity and pixel-center inclusion in that geometry after a valid vector-coordinate transformation into the reference raster CRS. The operation MUST NOT modify or resample source imagery.

#### Scenario: Pixel center inside study area
- **WHEN** a valid raster pixel center falls inside the configured study area
- **THEN** its prediction is retained if its required input bands are also valid

#### Scenario: Pixel center outside study area
- **WHEN** a pixel center falls outside the configured study area
- **THEN** hard, probability and uncertainty outputs mark it as NoData/invalid

#### Scenario: Study-area CRS is missing or transformation fails
- **WHEN** a study area exists but its CRS or a valid transformation to the raster CRS is unavailable
- **THEN** inference fails clearly and publishes no misleading output

#### Scenario: No study area configured
- **WHEN** the project has no study area
- **THEN** source raster validity alone controls the prediction mask

### Requirement: Input feature schema compatibility is explicit
A model's ordered input feature schema MUST be compared with every training and inference raster's declared schema. All Datasets contributing to one training run MUST share a compatible declared schema. Band count or feature-family identity alone MUST NOT be represented as proof of semantic compatibility. Unknown or mismatched feature identity MUST be handled by a clear failure or an explicit recorded override; the system MUST NOT silently assume equivalence between sensors or reordered bands.

#### Scenario: Ordered band metadata matches
- **WHEN** the selected raster's ordered schema matches the model's recorded schema
- **THEN** inference may proceed and record the schema identity in provenance

#### Scenario: Same count but incompatible or reordered bands
- **WHEN** the selected raster has the same number of bands but names/order or declared sensor/schema differ
- **THEN** inference fails or requires an explicit recorded override
- **AND** it does not claim compatibility based only on the count

#### Scenario: Training uses multiple Datasets
- **WHEN** one training run consumes samples from more than one Dataset
- **THEN** the ordered semantic feature schemas are validated before any samples are combined
- **AND** unlike schemas fail clearly rather than being concatenated by equal band count

#### Scenario: Checkpoint lacks semantic band identity
- **WHEN** a checkpoint records feature family/count but lacks ordered semantic band identity
- **THEN** compatibility is treated as unverified and requires an explicit recorded override
- **AND** no band names or sensor identity are fabricated

### Requirement: Raster outputs preserve source grid and validity
Pixel GeoTIFF outputs MUST preserve the selected reference region's dimensions, CRS, affine transform and bounds, use categorical integer values for hard labels, and consistently mark invalid pixels in hard, probability and uncertainty products. The source GeoTIFF MUST remain unchanged. Export files MUST be reopened and checked before they are made available.

#### Scenario: Full and partial-region exports
- **WHEN** a full raster or a bounded subregion is exported
- **THEN** the reopened outputs match the exact corresponding reference grid, including partial edge windows and rotated affine transforms

#### Scenario: Invalid source or study-area pixel
- **WHEN** a pixel is invalid under the combined validity mask
- **THEN** it carries the declared NoData value in all applicable output bands

#### Scenario: Export validation fails
- **WHEN** any reopened output fails grid/value integrity checks
- **THEN** failed artifacts are removed and are not published as successful exports

### Requirement: Processing limits are honest and enforced
The system MUST enforce configured processing limits before large allocations. Documentation and UI/API responses MUST NOT claim full-raster out-of-core processing while a path materializes whole-scene probability/output arrays.

#### Scenario: Request exceeds processing limit
- **WHEN** a raster exceeds the configured supported processing size
- **THEN** inference returns a clear error before allocating the prohibited full-scene arrays
- **AND** no partial export is published

#### Scenario: Request is within supported limit
- **WHEN** inference succeeds under the current processing implementation
- **THEN** its resource limitation is documented accurately unless all relevant paths have been verified as streaming
