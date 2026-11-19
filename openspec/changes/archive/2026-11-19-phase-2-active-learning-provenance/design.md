## Decisions

- **Batch is an immutable selection event.** Store request parameters, project/Dataset IDs, patch grid config, strategy and method, seed, model/training-run ID if used, strategy implementation version, creation time, candidate count plus a stable hash of the ordered eligible candidate IDs, and each selected item's stable sample ID, pixel window, geospatial coordinates if available, score/prediction/uncertainty/embedding reference as applicable. Link to Phase 3 immutable input/label hashes when available. Do not store huge candidate embeddings by default.
- **Decision state is mutable, history is not.** Query items transition through pending, labeled, rejected, or deferred. Record decision timestamp and optional annotator label/notes; no identity/authentication is implied. Label corrections remain versioned `Label` rows and reference the item that initiated them when possible.
- **Random baseline is reproducible.** Add `random` to strategy options, use an explicit seed from request or generated-and-returned seed, sample uniformly without replacement from exactly the valid/unlabeled candidate pool, and persist seed plus pool size. Candidate definition is shared across strategies.
- **Failure atomicity.** A failed query creates no partially populated batch. Persist selection and batch in one transaction after selection succeeds. Deleting a Dataset/project must cascade or explicitly retain historical metadata without dangling sensitive paths; never delete labels or source files unexpectedly.
- **Browser state is a view/cache.** Server batch records drive queue resume/history. Existing local unsaved drafts remain local until submitted and are visibly distinct from saved decisions.
- **Access scope.** In the absence of an auth system, batches are project-scoped like existing records. Do not add fake user IDs or claim multi-user collaboration.
- **Migration.** Add new tables and relationships with versioned idempotent additive migration; preserve old labels/query behavior and do not backfill historical batches that were never stored.

## Verification
Synthetic GeoTIFF/API/database tests cover all strategies, seeded repeatability, no-replacement, invalid/nodata exclusion, already-labeled exclusion, durable reload, decisions/corrections, failed-query atomicity, deletion and legacy query API compatibility. No external imagery/network.
