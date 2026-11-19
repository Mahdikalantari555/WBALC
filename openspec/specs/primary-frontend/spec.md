# primary-frontend Specification

## Purpose
Defines the project contract for primary frontend.

## Requirements

### Requirement: Canonical research frontend
The repository SHALL contain the primary SvelteKit application in `frontend/` with no duplicate app under `examples/`. Compose and the native launcher SHALL use that location.

#### Scenario: Start the primary app
- **WHEN** an operator builds or starts the frontend using the documented workflow
- **THEN** the workspace runs from `frontend/` and its same-origin API routes reach the configured backend
