## ADDED Requirements

### Requirement: Downloads are never silent stale output
`GET /projects/{id}/download/{type}` SHALL regenerate the artifact when the newest
export of that type predates the latest training run, and SHALL always report the
model iteration and staleness in response headers.

#### Scenario: Retrain then download
- **WHEN** a project is retrained after a map was exported
- **THEN** downloading the map again returns an artifact of the latest run and `X-RSAL-Export-Stale: false`

#### Scenario: Existing fresh export
- **WHEN** the newest export already belongs to the latest run
- **THEN** it is served as-is with `X-RSAL-Model-Iteration` set

### Requirement: Failure states cannot be mistaken for fresh results
The system SHALL report invariant violations explicitly (invalid checkpoint,
wrong feature schema, mismatched grid) instead of returning a generic server
error or an empty image.

#### Scenario: Incompatible checkpoint
- **WHEN** a checkpoint's feature schema does not match the requested inference
- **THEN** the request fails with a 409 and an actionable message naming the expected schema
