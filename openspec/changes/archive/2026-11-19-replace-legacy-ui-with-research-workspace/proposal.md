## Why

The SvelteKit workspace can review and train models but cannot start a study on an empty engine, and its recent-batch view is not a complete, portable research record. Maintaining two UIs also makes the default deployment ambiguous.

## What Changes

- Deploy the bilingual SvelteKit workspace as the only frontend; retire the Next.js application.
- Add project creation with an optional GeoJSON study boundary, GeoTIFF intake, and dated scene registration through same-origin adapters.
- Download an authoritative project research path (JSON) and a tabular sample ledger (CSV) from Active Learning, independent of browser state and the recent-history display limit.

## Capabilities

### New Capabilities
- `research-workspace`: Study intake and portable active-learning provenance in the default workspace.

## Impact

Container/native launchers, SvelteKit routes and bilingual forms, engine export routes, smoke tests, and operator documentation. Existing project storage remains unchanged.
