## ADDED Requirements

### Requirement: Each scene records its derived dataset
Every scene registration SHALL record the `Dataset` row it spawned
(`scenes.dataset_id`) and mark that row `origin='scene'`, so clients can target
the scene's raster for classification, queries and exports without guessing by
filename. Existing projects SHALL be backfilled deterministically from the
shared content digest.

#### Scenario: Registration links the pair
- **WHEN** a scene is uploaded and accepted
- **THEN** `GET /scenes` reports `dataset_id` for it and the derived dataset row carries `origin='scene'`

#### Scenario: Legacy projects are linked on migration
- **WHEN** the migration runs on a project registered before this change
- **THEN** each scene is linked to the dataset row with the same `content_sha256` (preferring the scene display-name form) and no row changes its file or path

#### Scenario: Derived dataset removal
- **WHEN** the derived dataset row is deleted through donor removal
- **THEN** the scene's `dataset_id` is nulled rather than left dangling
