## ADDED Requirements

### Requirement: The map states the classification resolution
The workspace SHALL display whether the painted classification/uncertainty field is
pixel-resolution or patch-cell resolution, together with the cell size, and SHALL
keep showing the previous field's stale state when a refresh fails.

#### Scenario: Pixel field displayed
- **WHEN** a pixel-resolution field is shown
- **THEN** the layer panel states pixel resolution and `1 cell = 1 px`

#### Scenario: Patch field displayed
- **WHEN** a patch field is shown
- **THEN** the layer panel states patch resolution and the patch size in pixels

### Requirement: The adapter forwards training options it exposes
The server adapter SHALL forward `resolution`, `evaluation_strategy`, `test_size` and
`params` to `POST /train`, SHALL forward `sample_resolution` when submitting
pixel-resolution point labels, and SHALL surface the resolution returned by training.

#### Scenario: Train request
- **WHEN** the workspace trains a project with a resolution selected
- **THEN** the backend receives that resolution and the response's resolution is available to the UI

#### Scenario: Pixel label
- **WHEN** a point label is submitted for pixel-mode training
- **THEN** the label request carries `sample_resolution: "pixel"` so distinct pixels in one patch are not merged
