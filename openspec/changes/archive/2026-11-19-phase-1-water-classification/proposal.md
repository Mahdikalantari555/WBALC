## Why

WBALC's project model already stores a three-class water-body taxonomy and binary interpretation, but the classifier still relies on generic project classes and exports the model's raw class codes. Configuration alone does not make a reproducible water-body product. Phase 1 makes the intended classes, label mapping, model outputs and optional binary recoding one explicit, testable contract.

## What Changes
- Make the canonical internal taxonomy `open_water`, `emergent_vegetation`, `land` the classifier's explicit WBALC configuration while retaining supported generic legacy projects.
- Add explicit label aliases/crosswalks, so alternate terms (including `reed`) are accepted only when mapped by a user and are not silently equated with emergent vegetation.
- Generate internal three-class classification/probability outputs and an optional derived binary product using the project's declared binary interpretation; keep original class output intact.
- Record taxonomy/config version and class order in training runs/checkpoints/exports; show class names and output interpretation consistently in the UI and legends.
- Define missing-class and partial-coverage behavior, and add synthetic tests.

## Capabilities
### New
- `water-class-taxonomy`
- `binary-water-interpretation`
### Modified
- `project-configuration`, `label-management`, `model-training`, `inference-export`.

## Impact
Project config validation, label resolution, training/checkpoint metadata, pixel/patch export semantics, legends and project UI. Use additive migration only if persisted config requires schema changes; never rewrite imagery.

## Non-goals
No temporal classification, area calculation, sensor harmonization/fusion, preprocessing, automated reed detection, accuracy claim, or replacement of generic legacy class lists without an explicit user migration.
