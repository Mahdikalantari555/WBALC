## MODIFIED Requirements

### Requirement: Real analytics with CSV export
The system SHALL display learning curve, confusion matrix and per-class metrics
from RSAL training runs, class distribution from current labels, and export
iteration metrics as CSV. It SHALL also list the classification and uncertainty
maps that exist for the project, with their dataset, layer, iteration and
staleness, and allow downloading each of them. No simulated metrics are shown.

#### Scenario: Analytics after training
- **WHEN** at least one RSAL training run exists
- **THEN** analytics shows the real curve/confusion/per-class data

#### Scenario: Export CSV
- **WHEN** the user exports analytics
- **THEN** a CSV of real iteration metrics downloads

#### Scenario: Maps section
- **WHEN** the project has exported maps
- **THEN** analytics lists them with dataset, layer type, iteration and stale state, and each is downloadable

#### Scenario: Empty maps section
- **WHEN** no map has been exported yet
- **THEN** analytics states that maps are produced after training and offers the map view as the entry point

### Requirement: TerraLab workspace shell
The system SHALL provide a single-page workspace in `frontend/` using the
TerraLab design (sidebar, topbar, projects/datasets/learning/analytics views)
with all data served by the RSAL backend, including the model-derived map
layers described by `map-overlays`.

#### Scenario: Workspace loads real projects
- **WHEN** the user opens the workspace with RSAL running
- **THEN** the sidebar and project dashboard list the projects from RSAL with derived stats (iteration, accuracy, labeled count)

#### Scenario: Backend unavailable
- **WHEN** RSAL is unreachable
- **THEN** the UI shows an actionable connection error and never fabricates demo data
