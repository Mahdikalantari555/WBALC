## ADDED Requirements

### Requirement: Reverse the current label without deleting history
Active Learning SHALL let an operator undo their most recent successful submission in the current review view. The backend SHALL only undo the requested version if it is still current in that project, keep its withdrawal timestamp in history and export, and exclude withdrawn versions from current labels and future training. Existing model runs SHALL remain unchanged.

#### Scenario: Undo a first submission
- **WHEN** an operator undoes the only retained label linked to a query item
- **THEN** the item returns to pending and the withdrawn version remains visible in the audit history

#### Scenario: Undo a revision
- **WHEN** an operator undoes a revision of a label
- **THEN** the previous retained version becomes current, with the corresponding prior decision restored for the same item when available

#### Scenario: Undo a superseded version
- **WHEN** a newer current label already exists or the requested version has been withdrawn
- **THEN** the API rejects the operation without changing the current label
