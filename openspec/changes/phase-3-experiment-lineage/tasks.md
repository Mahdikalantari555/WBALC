## 1. Audit/spec
- [x] 1.1 Audit TrainingRun, Dataset/Scene, labels, checkpoints, exports, metrics UI and current provenance fields.
- [x] 1.2 Define immutable manifest, legacy-incomplete behavior, hash and experiment-group decisions.

## 2. Dataset/artifact identity
- [ ] 2.1 Add streaming original-upload SHA-256 and Dataset/Scene schema/grid manifest; verify source-byte immutability.
- [ ] 2.2 Add checkpoint/export hashes after atomic write and reopened validation, with corruption/missing-file handling.
- [ ] 2.3 Add idempotent additive migration for nullable lineage fields and legacy incomplete status.

## 3. Run and experiment lineage
- [ ] 3.1 Create canonical manifest/hash service including dataset/scene, exact effective label versions, taxonomy, model, seed, evaluation and app/dependency identifiers.
- [ ] 3.2 Persist manifest immutable on each new TrainingRun; link relevant QueryBatch records and exports.
- [ ] 3.3 Add named Experiment model/config, run membership, API lifecycle and comparison endpoint.
- [ ] 3.4 Mark old runs/artifacts incomplete without fabricated history.

## 4. UI and verification
- [ ] 4.1 Show experiment/run lineage and metric comparisons in existing analytics UI.
- [ ] 4.2 Add synthetic tests for hashes, label correction, immutability, corruption, compare semantics and old-schema migration.
- [ ] 4.3 Verify secret/path exclusion, canonical serialization and failure-safe behavior.
- [ ] 4.4 Run backend/frontend verification and document exact outcomes and bitwise reproducibility limits.
