export interface ClassDefinition {
  id: string;
  name: string;
  color: string;
}
export type ProjectStatus = 'unlabeled' | 'in_progress' | 'completed';
export type BinaryOutputInterpretation = 'water_vs_non_water' | 'open_water_vs_other';
export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  classes: ClassDefinition[];
  studyAreaGeometry: Record<string, unknown> | null;
  studyAreaCrs: string | null;
  classificationConfig: {
    internalClasses: ['open_water', 'emergent_vegetation', 'land'];
    binaryOutputInterpretation: BinaryOutputInterpretation;
  };
  createdAt: string;
  iteration: number;
  accuracy: number;
  f1: number;
  labeledCount: number;
  totalSamples: number;
  modelVersion: string;
}
export type Bounds = [number, number, number, number];
export interface PixelWindow {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}
export type GeorefMode = 'map' | 'pixel';
export type GeorefReason = 'not-georeferenced' | 'unsupported-crs' | 'non-axis-aligned';

export interface Dataset {
  id: string;
  projectId: string;
  name: string;
  size: number;
  bands: number;
  width: number;
  height: number;
  resolution: string;
  crs: string;
  /** GDAL-style affine [a, b, c, d, e, f], when the file has one. */
  transform: number[] | null;
  /** WGS84 [w, s, e, n]; for pixel-space scenes [0, 0, width, height]. */
  bounds: Bounds;
  /** True when the scene has no usable CRS: displayed with Leaflet CRS.Simple. */
  pixelSpace: boolean;
  /** Why the dataset is (or is not) shown on the WGS84 basemap. */
  georefReason: GeorefReason | null;
  /** Patch grid the backend uses for this dataset, when known. */
  patchGrid: { patchSize: number; stride: number; rows: number; cols: number } | null;
  url: string;
  previewUrl: string | null;
  createdAt: string;
}
export type SatelliteSensor = 'Sentinel-1' | 'Sentinel-2';
export interface SceneMetadata {
  id: string;
  projectId: string;
  acquisitionDateTime: string | null;
  platform: string | null;
  sensor: SatelliteSensor;
  productType: string | null;
  productLevel: string | null;
  processingBaseline: string | null;
  nativeBandResolutions: Record<string, number> | null;
  sourceFilename: string;
  crs: string | null;
  transform: number[] | null;
  width: number;
  height: number;
  pixelSizeX: number | null;
  pixelSizeY: number | null;
  resolutionX: number | null;
  resolutionY: number | null;
  bandCount: number;
  bandNames: (string | null)[] | null;
  bandDescriptions: (string | null)[] | null;
  bandDtypes: string[] | null;
  nodataValues: (number | null)[] | null;
  hasValidityMask: boolean;
  bounds: Bounds | null;
  polarization: string[] | null;
  acquisitionMode: string | null;
  orbitDirection: string | null;
  relativeOrbit: number | null;
  productReference: string;
  uploadedAt: string;
  registeredAt: string;
  sizeBytes: number;
}
export interface SceneUploadMetadata {
  sensor: SatelliteSensor;
  acquisitionDateTime?: string;
  platform?: string;
  productType?: string;
  productLevel?: string;
  polarization?: string;
  acquisitionMode?: string;
  orbitDirection?: 'ascending' | 'descending';
  relativeOrbit?: string;
  processingBaseline?: string;
  nativeBandResolutions?: string;
}

export interface SampleGeometry {
  type: 'Point' | 'Polygon';
  coordinates: number[] | number[][][];
}
export interface Sample {
  id: string;
  projectId: string;
  lat: number;
  lng: number;
  prediction: string;
  confidence: number;
  uncertainty: number;
  status: 'pending' | 'labeled' | 'skipped';
  label: string | null;
  note: string;
  iteration: number;
  batchIndex: number;
  /** Display-space geometry (WGS84, or pixel-display when the scene has no CRS). */
  geometry: SampleGeometry | null;
  source: 'query' | 'manual' | 'import';
  datasetId?: string;
  /** Pixel window of this sample's patch in the source raster, when known. */
  window?: PixelWindow;
  /** Top-left pixel of the patch (the point a label is attached to). */
  pixel?: { x: number; y: number };
  /** Display-space patch rectangle [w, s, e, n]. */
  bbox?: Bounds;
  /** True when the backend has a stored label for this sample. */
  saved?: boolean;
}
export interface LabelInput {
  sampleId: string;
  /** Dataset the sample belongs to; drafts drawn on a scene keep it forever. */
  datasetId?: string;
  label: string | null;
  status: 'labeled' | 'skipped';
  note: string;
  lat?: number;
  lng?: number;
  geometry?: SampleGeometry | null;
  pixel?: { x: number; y: number };
  /** Set to "pixel" when the project trains at pixel resolution, so distinct
   * points inside one patch keep distinct sample identities. */
  sampleResolution?: 'pixel' | 'patch';
}
export interface Iteration {
  id: string;
  projectId: string;
  number: number;
  accuracy: number;
  f1: number;
  sampleCount: number;
  labeledCount: number;
  createdAt: string;
}
export interface ClassMetrics {
  name: string;
  color: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}
export interface Metrics {
  accuracy: number;
  f1: number;
  labeledCount: number;
  totalSamples: number;
  iteration: number;
  curve: Iteration[];
  distribution: { name: string; color: string; value: number }[];
  confusionMatrix: number[][];
  perClass: ClassMetrics[];
  evaluation: string;
}
export interface CreateProjectInput {
  name: string;
  description: string;
  classes: ClassDefinition[];
  studyAreaGeometry?: Record<string, unknown> | null;
  studyAreaCrs?: string | null;
  classificationConfig?: {
    internalClasses: ['open_water', 'emergent_vegetation', 'land'];
    binaryOutputInterpretation: BinaryOutputInterpretation;
  };
}
export type WorkspaceView = 'projects' | 'datasets' | 'unsupervised' | 'learning' | 'analytics';
export type DrawingTool = 'pan' | 'point' | 'polygon' | 'rectangle';
export type BandMode = 'true-color' | 'false-color' | 'ndvi' | 'custom';

/** Model-derived map layers, toggleable in the map view. */
export type MapLayer = 'hard' | 'uncertainty';
export type UncertaintyMethod = 'entropy' | 'margin' | 'least_confidence';
export type MapExportFormat = 'tif' | 'png' | 'csv';

/** A grid-aligned field returned by the map adapter. */
export interface MapField {
  layer: MapLayer;
  method: string | null;
  projectId: string;
  datasetId: string;
  modelIteration: number;
  trainingRunId: number;
  classes: string[];
  /** "pixel" = one independent prediction per source pixel; "patch" = one per
   * patch cell (block-filled over its pixel window, not per-pixel inference). */
  resolution: 'pixel' | 'patch';
  /** Class colours from the backend palette (same colours the exports use). */
  colors: string[];
  grid: { rows: number; cols: number; patchSize: number; stride: number };
  /** rows x cols; null where the patch has no valid pixels. */
  values: (number | null)[][];
  valid: boolean[][];
  min: number;
  max: number;
  /** True when a newer training run exists than the one this field came from. */
  stale: boolean;
}

export interface LayerSettings {
  visible: boolean;
  opacity: number;
}
export interface RasterMetadata {
  bands: number;
  width: number;
  height: number;
  resolution: string;
  crs: string;
  bounds: Bounds | null;
}
export type SomColorMode = 'u-matrix' | 'classes' | 'spectral' | 'density' | 'uncertainty';
export interface SomCell {
  row: number;
  col: number;
  hitCount: number;
  labeledCount: number;
  unlabeledCount: number;
  uValue: number;
  quantizationError: number;
  dominantLabel: string | null;
  labelCounts: Record<string, number>;
  predictedClass: string | null;
  predictionCounts: Record<string, number>;
  meanConfidence: number | null;
  meanUncertainty: number | null;
  bandMeans: number[];
  bandProfile: number[];
  representativeSampleId: string | null;
  sampleIds: string[];
}
export interface SomData {
  projectId: string;
  datasetId: string;
  rows: number;
  cols: number;
  epochs: number;
  totalPatches: number;
  labeledPatches: number;
  activeNeurons: number;
  quantizationError: number;
  topographicError: number;
  modelIteration: number | null;
  bands: number;
  classes: string[];
  uMatrix: number[][];
  hitGrid: number[][];
  cells: SomCell[];
}
export interface SomQueryOptions {
  somRows?: number;
  somCols?: number;
  somEpochs?: number;
  somCell?: [number, number];
}
export type SomPaletteMode = 'distinct' | 'topological' | 'spectral';
export interface SomClusterSummary {
  clusterId: number;
  label: string;
  color: [number, number, number];
  pixelCount: number;
  fraction: number;
  bandMeans: number[];
  bandProfile: number[];
  neurons: [number, number][];
}
export interface SomClassifyInput {
  datasetId?: string;
  rows: number;
  cols: number;
  nClusters?: number | null;
  epochs?: number;
  resolution?: 'pixel' | 'patch';
}
export interface SomClassification {
  projectId: string;
  datasetId: string;
  exportId: number;
  rows: number;
  cols: number;
  epochs: number;
  nClusters: number;
  resolution: 'pixel' | 'patch';
  shape: [number, number];
  totalValid: number;
  nodataCount: number;
  quantizationError: number;
  topographicError: number;
  uMatrix: number[][];
  neuronClusters: number[][];
  neuronHits: number[][];
  clusters: SomClusterSummary[];
  downloadUrl: string;
}
