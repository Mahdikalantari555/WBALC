## MODIFIED Requirements

### Requirement: Classification layer
The map SHALL provide a classification layer that paints the model's predicted
class for the *active raster* — the training raster or any scene date — using
the same class colours as the legend. The layer entry SHALL always be listed;
for a raster that the latest run has not classified it SHALL present an
explicit unclassified state with a per-raster classify action instead of being
hidden or silently blank.

#### Scenario: Toggle classification on
- **WHEN** the analyst enables the classification layer with a trained model present and a field available for the active raster
- **THEN** the map paints every valid cell of the active raster with its predicted class colour and the legend lists the classes shown

#### Scenario: Toggle classification off
- **WHEN** the analyst disables the classification layer
- **THEN** the classification overlay is removed and samples, footprints and imagery are unaffected

#### Scenario: No trained model
- **WHEN** the classification layer is requested for a project without a trained model
- **THEN** the layer is not enabled and the UI explains that training is required first

#### Scenario: Invalid patches
- **WHEN** a cell is entirely nodata in the source raster
- **THEN** it is rendered transparent and is not counted as a classified cell

#### Scenario: Classification on a scene date
- **WHEN** the analyst selects an acquisition date on the map and enables classification
- **THEN** the field is inferred for that scene's own dataset and painted on it, exactly as for the training raster

#### Scenario: Date not yet classified
- **WHEN** the active date has no classification field for the latest run
- **THEN** the layer row shows a muted "not classified for this date" state with a "Classify this date" action, and the toggle cannot be switched on until a field arrives

#### Scenario: Date switch with the layer enabled
- **WHEN** the analyst switches dates while classification is enabled
- **THEN** the field for the new date loads automatically (cache permitting) and repaints without a page refresh

### Requirement: Layer scope and staleness
Model-derived layers SHALL be scoped to the active raster and the training run
that produced them, and SHALL report when a newer run exists. Layer provenance
SHALL come from the field response itself (run/iteration/resolution), never
from the client's assumption about which run is latest.

#### Scenario: Dataset switch
- **WHEN** the analyst switches the map to another dataset — including any scene date
- **THEN** the layers are refreshed for that dataset or reported as unavailable/not-yet-classified for it, never drawn from the previous dataset

#### Scenario: Stale map
- **WHEN** the project has a newer training run than the one that produced the displayed layer
- **THEN** the panel and legend mark the layer as stale and offer a refresh

#### Scenario: Provenance matches the product
- **WHEN** the identity panel describes the painted field
- **THEN** the run/iteration and pixel-versus-patch resolution it reports are the ones the field response recorded
