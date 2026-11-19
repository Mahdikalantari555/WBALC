## ADDED Requirements

### Requirement: Single research workspace
The default deployment SHALL serve the bilingual SvelteKit frontend without a Next.js service.

#### Scenario: Default startup
- **WHEN** an operator launches the default stack
- **THEN** the SvelteKit workspace is available and communicates with the engine via same-origin routes

### Requirement: Study intake and learning
The workspace SHALL support creating a project with an optional study boundary, uploading a GeoTIFF or registering a dated scene, and continuing to the existing map and active learning workflow.

#### Scenario: Empty engine
- **WHEN** an operator opens the workspace without projects
- **THEN** they can create a project, upload data, request samples, annotate, and train without leaving the interface

### Requirement: Exportable research path
The workspace SHALL expose JSON and CSV downloads derived from persisted project records. All sampling batches SHALL be included regardless of the recent-history limit. Each batch SHALL distinguish selected samples, labeled decisions, and retained first-version labels; each exported sample SHALL retain pixel position, available CRS coordinates, uncertainty, prediction, and decision without substituting missing values.

#### Scenario: Export after several rounds
- **WHEN** an operator downloads the research path after annotating and training
- **THEN** the export includes older and newer batches, query-time values, and explicit run references, and the JSON also contains training and retained label provenance
