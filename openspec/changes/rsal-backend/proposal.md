## Why

Satellite image classification with active learning reduces labeling cost by selecting informative samples. No backend currently exists to manage projects, datasets, labels, AL queries, training, and inference.

## What Changes

- New FastAPI backend for project/dataset/label management
- GeoTIFF ingestion with metadata extraction
- Active learning query engine (uncertainty, diversity, hybrid)
- Model training (classical RF/LightGBM first) with metrics
- Inference and GeoTIFF export
- SQLite-backed persistence, synchronous training for MVP

## Capabilities

### New Capabilities
- `project-management`: create/read/update projects with classes
- `dataset-ingestion`: upload GeoTIFF and store metadata
- `label-management`: store/correct labels with history
- `active-learning-query`: batch query strategies
- `model-training`: train classical models and store metrics
- `inference-export`: predict and export GeoTIFF

### Modified Capabilities
- (none)

## Impact

- New codebase under app/
- Dependencies: FastAPI, SQLAlchemy, rasterio, scikit-learn, numpy
- Storage directory for uploads and models
