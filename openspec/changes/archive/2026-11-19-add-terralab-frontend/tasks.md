## 1. Backend additions
- [x] 1.1 Serve original GeoTIFF: GET /projects/{id}/dataset/{dataset_id}/file
- [x] 1.2 Extended dataset metadata: size_bytes + patch grid fields (computed)
- [x] 1.3 Dataset deletion with file/labels/exports cleanup
- [x] 1.4 Label deletion: DELETE /projects/{id}/labels/{sample_id} (all versions)
- [x] 1.5 Tests for all additions; full backend suite green

## 2. Frontend foundation
- [x] 2.1 Scaffold frontend/ from TerraLab (design system, shell, views)
- [x] 2.2 Strip demo backend: db/, repository, demo seed, Drizzle/pg deps, SATELLITE_API_URL proxy
- [x] 2.3 RSAL adapter (BFF): projects/stats, upload, dataset list/delete/file, query, labels, train, metrics, import, health
- [x] 2.4 Client wiring: persisted batch store replaces /predictions; strategy mapping; cold-start diversity

## 3. Feature work
- [x] 3.1 Map: WGS84 + pixel-space fallback, band modes on real uploaded rasters
- [x] 3.2 Review: keyboard shortcuts (classes 1-9, submit, skip, navigate)
- [x] 3.3 Label import: GeoJSON/CSV with class mapping + reprojection (ported from TerraLoop)
- [x] 3.4 Label correction + deletion UI
- [x] 3.5 Analytics: real learning curve/confusion/per-class; CSV export; drop simulated confidence drift

## 4. Integration & quality
- [x] 4.1 Env/docs: frontend .env.example, root README, compose frontend service
- [x] 4.2 Typecheck + production build green
- [x] 4.3 Live end-to-end smoke through the adapter against real RSAL
- [x] 4.4 Live preview for review

## 5. Cleanup
- [x] 5.1 Delete satellite-active-learning-frontend/
- [x] 5.2 Delete satellite-image-classification-frontend/
