## ADDED Requirements
### Requirement: sample preview preserves source shape
The sample-review panel SHALL show a raster crop without distorting its width-to-height ratio. Rectangular or edge-clamped sample windows SHALL remain rectangular in the preview; unused preview area may be letterboxed. The crosshair SHALL indicate the sample center without implying the letterboxed box is the raster window boundary.

#### Scenario: rectangular patch preview
- GIVEN a sample window wider or taller than the review card
- WHEN its GeoTIFF crop is rendered
- THEN the crop is contained and its native aspect ratio remains unchanged.
