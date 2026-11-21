## ADDED Requirements

### Requirement: Manual samples from the map
The map SHALL let the analyst turn any probed pixel of the active raster into a
new labeled sample — with a class chosen from the project taxonomy — without
requiring that pixel to come from a query batch. The submission SHALL be a
pixel-space point label on the active dataset with manual provenance, and the
engine SHALL derive the sample identity for the pixel, so re-labeling the same
pixel revises the same sample instead of duplicating it.

#### Scenario: Label a pixel no batch proposed
- **WHEN** the analyst probes a pixel that no query batch proposed and submits the manual-sample form with a class
- **THEN** a manual point label at that pixel is stored on the active dataset and it appears in the samples layer and label history

#### Scenario: Relabeling the same pixel
- **WHEN** the analyst labels a pixel that already carries a manually created label
- **THEN** the submission becomes a new version of that same sample, not a second sample

#### Scenario: Scene raster without a dataset row
- **WHEN** the active raster is a legacy scene view with no derived dataset row
- **THEN** the manual-sample action is unavailable with an explanation, because a label needs a registered dataset to attach to
