## Why
The production SvelteKit app should live at the repository's canonical frontend path, not under examples.

## What Changes
Move the app to `frontend/` and point build, launch and compatibility checks there. Preserve its runtime behavior and routes.

## Capabilities
### New Capabilities
- `primary-frontend`: Canonical location and local deployment contract for the research workspace.

## Impact
Compose build context, native launcher, integration checks and documentation; no API or database migration.
