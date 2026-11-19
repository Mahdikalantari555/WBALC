## Context

Greenfield FastAPI backend. SQLite for MVP, synchronous training, classical models first.

## Goals / Non-Goals

**Goals:** Clean architecture, all required endpoints, active learning strategies, metrics storage.
**Non-Goals:** Production Celery, deep models, frontend.

## Decisions

- SQLAlchemy async + SQLite (aiosqlite) for dev; Postgres supported via env.
- Classical RF via scikit-learn first; CNN optional later.
- Active learning operates on patch-level embeddings/probabilities.
- Storage on local filesystem under STORAGE_DIR.

## Risks / Trade-offs

- Synchronous training blocks request → mitigate with timeouts and small datasets.
- SQLite concurrency limits → migrate to Postgres for production.

## Migration Plan

Deploy via Docker compose; run init_db on startup.

## Open Questions

- Patch extraction window size and stride.
