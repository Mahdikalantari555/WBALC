## Why
Operators need to inspect the original pixel behind a preview, visually compare dates without losing map position, and correct accidental annotations without deleting their history.

## What Changes
- Read native raster values and NoData on map click.
- Swipe between aligned acquisitions in one map viewport.
- Undo the most recent label submission in Active Learning through a project-scoped, history-preserving endpoint.

## Capabilities
### New Capabilities
- `map-inspection`: Native pixel probes and aligned visual comparison.

### Modified Capabilities
- `label-management`: Reversible label submissions and retained audit history.

## Impact
SvelteKit map and review, label API, and an additive `labels.undone_at` migration. Existing training checkpoints are unchanged.
