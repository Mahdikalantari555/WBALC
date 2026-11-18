## ADDED Requirements

### Requirement: Classification layer
The map SHALL provide a classification layer that paints the model's per-patch
class for the active dataset, using the same class colours as the legend.

#### Scenario: Toggle classification on
- **WHEN** the analyst enables the classification layer with a trained model present
- **THEN** the map paints every valid patch cell with its predicted class colour and the legend lists the classes shown

#### Scenario: Toggle classification off
- **WHEN** the analyst disables the classification layer
- **THEN** the classification overlay is removed and samples, footprints and imagery are unaffected

#### Scenario: No trained model
- **WHEN** the classification layer is requested for a project without a trained model
- **THEN** the layer is not enabled and the UI explains that training is required first

#### Scenario: Invalid patches
- **WHEN** a patch is entirely nodata in the source raster
- **THEN** its cell is rendered transparent and is not counted as a classified cell

### Requirement: Uncertainty layer
The map SHALL provide an uncertainty layer that paints per-patch uncertainty
computed from the model's class probabilities, with a selectable method.

#### Scenario: Toggle uncertainty on
- **WHEN** the analyst enables the uncertainty layer
- **THEN** the map paints each valid patch cell with a value in [0, 1] on a continuous ramp, with a legend showing the value range

#### Scenario: Method selection
- **WHEN** the analyst switches the method between entropy, margin and least confidence
- **THEN** the layer is refreshed with that method and the legend states which method is shown

#### Scenario: Consistent with the query ranking
- **WHEN** the uncertainty layer is shown for the same run and method as a query batch
- **THEN** the patches in that batch are among the highest-uncertainty cells on the layer

#### Scenario: Cell readout
- **WHEN** the pointer hovers a cell of the uncertainty layer
- **THEN** the UI reports that cell's uncertainty value and its predicted class

### Requirement: Layer independence
Classification and uncertainty layers SHALL be independently controllable and
independent of the imagery, suggestion and label layers.

#### Scenario: Independent opacity
- **WHEN** the analyst changes the opacity of a model-derived layer
- **THEN** only that layer's opacity changes, and imagery/labels/other layers keep theirs

#### Scenario: Both at once
- **WHEN** both layers are enabled
- **THEN** they render in a defined order (classification below uncertainty) and the legend names both

### Requirement: Layer scope and staleness
Model-derived layers SHALL be scoped to the active dataset and the training run
that produced them, and SHALL report when a newer run exists.

#### Scenario: Dataset switch
- **WHEN** the analyst switches the map to another dataset
- **THEN** the layers are refreshed for that dataset or reported as unavailable for it, never drawn from the previous dataset

#### Scenario: Stale map
- **WHEN** the project has a newer training run than the one that produced the displayed layer
- **THEN** the panel and legend mark the layer as stale and offer a refresh

### Requirement: Layer export
The system SHALL export each model-derived layer as GeoTIFF, PNG and CSV.

#### Scenario: Export classification GeoTIFF
- **WHEN** the analyst exports the classification layer
- **THEN** a single-band GeoTIFF downloads whose values are 0-based class indices, whose colormap matches the UI class colours, and whose `classes` tag lists the class names

#### Scenario: Export uncertainty GeoTIFF
- **WHEN** the analyst exports the uncertainty layer
- **THEN** a single-band float32 GeoTIFF downloads with values in [0, 1] and a `method` tag naming the uncertainty method

#### Scenario: Export PNG snapshot
- **WHEN** the analyst exports the current layer as PNG
- **THEN** the PNG contains exactly the cells and colours of the layer on screen, including transparency for invalid cells

#### Scenario: Export CSV table
- **WHEN** the analyst exports the layer as CSV
- **THEN** the CSV has one row per grid cell with row, col, pixel window, predicted class, uncertainty value (when applicable) and a validity flag

#### Scenario: Export without a model
- **WHEN** an export is requested for a project without a trained model
- **THEN** the request fails with a documented error and no partial file is produced

#### Scenario: Exported geometry matches the source scene
- **WHEN** an exported map GeoTIFF is opened next to its source GeoTIFF
- **THEN** cell (row, col) covers the same ground as the patch that row and col describe, including edge cells that are clamped to the image edge

## MODIFIED Requirements

### Requirement: Probability and hard maps
The system SHALL return probability maps and hard classification maps.

#### Scenario: Map outputs
- **WHEN** inference runs
- **THEN** system returns probability and hard class maps

#### Scenario: Uncertainty field available
- **WHEN** inference runs for display purposes
- **THEN** the system can return a grid-aligned uncertainty field and a per-cell validity mask without returning the full class-probability tensor

### Requirement: GeoTIFF export
The system SHALL export results as GeoTIFF.

#### Scenario: Export GeoTIFF
- **WHEN** GET /projects/{project_id}/download/{type} with export type
- **THEN** system returns GeoTIFF result

#### Scenario: Uncertainty export type
- **WHEN** GET /projects/{project_id}/download/uncertainty with an uncertainty method
- **THEN** system returns a float32 GeoTIFF of the uncertainty field for the requested method

#### Scenario: Colour contract
- **WHEN** any hard classification GeoTIFF or PNG is exported
- **THEN** its colormap is the same deterministic palette the workspace uses for class display
