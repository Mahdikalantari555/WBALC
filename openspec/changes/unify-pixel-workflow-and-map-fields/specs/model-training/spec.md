## ADDED Requirements

### Requirement: Run listing is newest-first and iterations are server-owned
`GET /projects/{id}/runs` SHALL return training runs ordered by descending
iteration (ties by descending id), matching the engine's own latest-run
selection. `POST /train` SHALL derive `iteration` as one greater than the
project's current maximum and SHALL NOT use a client-supplied iteration value
for run identity; the response SHALL report the derived iteration.

#### Scenario: Frontend picks the actual latest run
- **WHEN** a project has a patch run at iteration 0 and a pixel run at iteration 1
- **THEN** the runs list starts with the pixel run, and the workspace's latest-run pointer, field cache identity and arena primary all reference it

#### Scenario: Client cannot create duplicate iterations
- **WHEN** two train requests arrive with the same or conflicting `iteration` values
- **THEN** the runs created receive successive server-derived iterations and both responses state the iteration actually used

#### Scenario: History display order
- **WHEN** an operator opens the run history or the arena
- **THEN** the newest run appears first without any client-side re-sorting
