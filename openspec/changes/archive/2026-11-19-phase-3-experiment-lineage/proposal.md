## Why

Metrics and checkpoints are saved, but a score is not fully reproducible from current database records: Dataset IDs do not prove which bytes/band metadata were used, label versions are not snapshotted, query batches are not linked, and run/checkpoint artifact integrity is not recorded. Phase 3 completes scientific data lineage and allows controlled runs to be grouped and compared.

## What Changes
- Add immutable Dataset version manifests (content hash, source metadata/schema, registration version) without altering source bytes.
- Record training label snapshot (ordered label-version identifiers/hash), input Dataset manifests, config, evaluation protocol, code/dependency version and deterministic parameters on every run.
- Verify and record model checkpoint and export hashes; link exports and Phase 2 query batches to their producing run/experiment.
- Add named Experiment groups and immutable run membership/config snapshots, plus compare/list/detail APIs and UI.
- Mark old runs as legacy/incomplete where provenance is unavailable; never synthesize missing history.

## Capabilities
### New: `dataset-lineage`, `experiment-management`, `artifact-integrity`
### Modified: `model-training`, `inference-export`, `query-batch-provenance`, `analytics`.

## Impact
Additive database migrations, upload hashing/metadata, training and export manifests, query linkage, APIs and history UI. Keep immutable uploaded imagery and local storage conventions; no new job framework.

## Non-goals
No distributed execution, workflow scheduler, access-control system, automatic paper generation, or claims of bitwise reproducibility across unsupported hardware/library versions. Research protocol evaluation is Phase 5.
