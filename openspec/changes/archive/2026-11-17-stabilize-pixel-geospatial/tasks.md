## 1. Raster correctness
- [x] 1.1 Exact grid compatibility helper and unit regression tests
- [x] 1.2 Mask-aware raster reads and exhaustive patch validity
- [x] 1.3 Pixel categorical outputs validated after writing/reopening
- [x] 1.4 Non-divisible dimensions, rotated affine, non-square pixels, non-default CRS and NoData tests

## 2. Pixel-level supervised model
- [x] 2.1 Explicit patch/pixel request and checkpoint feature contract
- [x] 2.2 Point/polygon pixel targets, identity and bounds checks
- [x] 2.3 Direct pixel inference, block-window input reads, exact source-grid exports
- [x] 2.4 RF and LightGBM pixel regression plus patch compatibility tests

## 3. Evaluation
- [x] 3.1 Spatial grouped holdout with explicit insufficient-data state
- [x] 3.2 IoU, seed, feature/evaluation configuration and dataset identifiers
- [x] 3.3 Spatial holdout and metrics regression coverage

## 4. Label integrity
- [x] 4.1 Finite values, polygon ring closure/self-intersection, class/bounds checks, pixel identity and declared-CRS transformation
- [x] 4.2 Regression coverage for invalid/out-of-bounds labels and CRS transformation

## 5. Sample review display correctness
- [x] 5.1 Replace stretched background with aspect-preserving contained image; remove misleading full-card crop border
- [x] 5.2 Verify typecheck, lint, frontend tests, and production build

## 6. Documentation, licensing, verification
- [x] 6.1 README and audit updated; MIT license added with user-confirmed holder
- [x] 6.2 Python/frontend dependency license inventory and notable restrictions documented in `THIRD_PARTY_LICENSES.md`
- [x] 6.3 Complete backend suite and frontend checks run
- [x] 6.4 Archive implemented change; remaining production/legal recommendations are documented in audit and license inventory

## Accepted follow-up risks
The archived change does not claim to solve full OGC polygon topology validation, streaming the full probability output, domain-specific spatial-block sizes, legacy patch-grid export equivalence, or legal review of third-party custom terms. These are documented in `AUDIT.md` and `THIRD_PARTY_LICENSES.md` and should be resolved before large-scale production redistribution/use.
