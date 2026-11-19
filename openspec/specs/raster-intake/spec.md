# raster-intake Specification

## Purpose
Defines editable classes, reviewed band identity, and dataset-scoped raster previews.

## Requirements

### Requirement: User-defined classes
The workspace SHALL start a new project with editable water and non-water classes and SHALL support adding further unique class names without a four-class UI cap. Appending a class SHALL NOT change earlier checkpoint class order.

#### Scenario: Expand a project after training
- **WHEN** a new class is appended to a trained project
- **THEN** prior predictions use only the recorded run class order and the added class is available for new labels and retraining

### Requirement: Review ordered band identity before import
The workspace SHALL expose a name for each band of a multiband GeoTIFF, or for each single-band file in a staged stack. The engine SHALL reject mismatched native grids instead of resampling them silently.

#### Scenario: Optical and radar dated folders
- **WHEN** a folder with dated GeoTIFF groups and recognized JSON metadata is selected
- **THEN** the workspace stages separate acquisitions, proposes ordered band names, records recognized timestamps, and reports each import independently

#### Scenario: One invalid acquisition
- **WHEN** one staged acquisition has mismatched dimensions, CRS, or transform
- **THEN** that acquisition is not saved and already successful acquisitions are not retried in the same session

### Requirement: Dataset-scoped layer previews
The map SHALL allow previewing dated scenes and training rasters and selecting their source bands and creating or removing normalized-difference previews. The previews SHALL NOT change the source raster or look like model-derived downloads.

#### Scenario: Radar raster selected
- **WHEN** the current raster has only VV and VH bands
- **THEN** the UI offers individual radar bands without presenting optical NDVI or RGB as valid presets
