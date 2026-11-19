## ADDED Requirements

### Requirement: Map action and imagery context
Unavailable map export and layer creation controls SHALL explain their prerequisites. The map SHALL announce the selected band, composite, or named derived preview and distinguish hidden imagery from a selected layer.

#### Scenario: No model exists
- **WHEN** a training raster is selected with no trained model
- **THEN** export is disabled and adjacent text links the user to Active Learning

### Requirement: Review and navigate imported imagery
The import review SHALL label filename-derived suggestions separately from operator confirmation and provide a filter for unconfirmed or invalid groups. Successful imports SHALL offer direct navigation to the exact raster or scene.

#### Scenario: Mixed batch result
- **WHEN** one group imports but another fails
- **THEN** the successful group offers Show on map and the failed group remains in the review filter

### Requirement: Recover local naming drafts
The UI SHALL offer explicit recovery of unfinished class names and band mappings across refreshes. Band drafts SHALL match project, import type, and ordered file metadata; uploaded files SHALL NOT be persisted and successful submissions SHALL clear their drafts.

#### Scenario: Recover an unfinished mapping
- **WHEN** the operator refreshes and reselects the same files in the same order
- **THEN** the saved names are offered for recovery without automatically uploading or restoring files
