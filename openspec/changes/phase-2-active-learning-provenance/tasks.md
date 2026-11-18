## 1. Audit/spec
- [x] 1.1 Audit Label history, query strategies, browser queue and data model.
- [x] 1.2 Define batch/item state and seeded random baseline without implying collaboration.

## 2. Persistence/API
- [ ] 2.1 Add QueryBatch and QueryItem models, safe foreign-key/cascade policy and additive migration.
- [ ] 2.2 Persist query parameters, candidate pool metadata, strategy result order/score, seed and model run provenance atomically.
- [ ] 2.3 Add seeded random sampling to query schema/service and ensure common candidate eligibility.
- [ ] 2.4 Add batch list/detail/resume endpoints and durable decision transitions.
- [ ] 2.5 Link saved/corrected labels to originating query items without breaking manual/legacy label submission.

## 3. UI
- [ ] 3.1 Use backend batch as source of truth for review queue; distinguish local drafts from submitted decisions.
- [ ] 3.2 Add strategy selection including random, batch history, resume and decision actions.
- [ ] 3.3 Surface seed/strategy/model/Dataset summary and gracefully support no-auth single-workspace mode.

## 4. Verification
- [ ] 4.1 Add synthetic tests for repeatability, no replacement, invalid-pixel exclusion and common candidate pool.
- [ ] 4.2 Test persistence across clients/reloads, decision transitions, label linkage, correction history and failed-query atomicity.
- [ ] 4.3 Test migration from existing schemas and legacy queries/labels.
- [ ] 4.4 Run backend/frontend suites and document results and collaboration limitations.
