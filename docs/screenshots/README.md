# Research workspace verification

Local captures are excluded from Git; the links below work only when the images
are present in this workspace. These captures are from the production Node build connected to a live FastAPI
engine, using a synthetic four-band GeoTIFF in a temporary project. They are not
examples of measured land-cover accuracy.

- [Project and data — desktop](project-data-desktop.png): a study was created
  with a WGS84 boundary and its first raster was uploaded.
- [Active Learning — desktop](active-learning-desktop.png): 12 suggestions were
  selected before training and 9 labels were added. A second round requested 6
  uncertainty-ranked suggestions from the trained checkpoint. JSON and CSV were
  downloaded and checked against the recorded counts, CRS, scores, and run ID.
- [Project and data — Persian mobile](project-data-mobile-fa.png): RTL layout at
  390 px. Horizontal overflow was checked on both intake and Active Learning.

The browser walkthrough also registered a dated scene. Run the adapter contract
smoke test against a running stack with:

```sh
.venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:3000
```
