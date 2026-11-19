# Phase 2 audit — Annotation and Active Learning

Audit date: 2026-11-18. Read-only review; no code/tests changed or run.

## Existing foundation
- Labels persist in `Label` with project/Dataset/sample identity, geometry, class, iteration, correction version and timestamps; history endpoints exist.
- Query endpoint supports uncertainty, diversity, hybrid and SOM over valid patch embeddings; uncertainty can use least-confidence, margin or entropy. Cold-start diversity exists.
- Point/polygon labels can identify pixels, but active-learning query candidates are patch-grid based.
- The review queue is persisted in browser localStorage; labels become server-durable only when submitted.

## Gaps
- No `QueryBatch`/query-item persistence, candidate snapshot, decision status, or durable association between selected suggestions and later labels.
- No random-sampling baseline.
- Query request parameters/seed/model/Dataset/candidate counts and exact selection results are not retained as an immutable scientific record.
- No shared multi-annotator workflow or authentication/authorization model; this phase must not imply one.

## Phase boundary
Phase 2 makes sampling batches and annotation decisions durable and comparable while retaining the existing patch-grid sampling basis. It does not add account management, multi-user permissions, pixel candidate AL, or experiment-wide lineage (Phase 3).
