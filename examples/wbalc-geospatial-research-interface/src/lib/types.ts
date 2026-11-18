/**
 * Browser-facing view models.
 *
 * The adapter (`src/lib/server/adapter.ts`) converts RSAL payloads into these
 * shapes, and only these shapes reach components. They carry the provenance the
 * UI needs to stay honest: which run, which resolution, which evaluation
 * protocol, which dataset.
 */
import type { Bounds, GeorefReason, PixelWindow } from './geo';

export type BinaryInterpretation = 'water_vs_non_water' | 'open_water_vs_other';

export interface ProjectView {
  id: string;
  name: string;
  description: string;
  status: string;
  classes: string[];
  classificationConfig: {
    internalClasses: string[];
    binaryOutputInterpretation: BinaryInterpretation;
  };
  studyAreaGeometry: Record<string, unknown> | null;
  studyAreaCrs: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface DatasetView {
  id: string;
  projectId: string;
  name: string;
  /** `/api/projects/{project}/datasets/{dataset}/file` — always the adapter. */
  url: string;
  crs: string | null;
  transform: number[] | null;
  width: number;
  height: number;
  bands: number;
  dtype: string;
  nodata: number | null;
  bounds: Bounds | null;
  sizeBytes: number;
  createdAt: string;
  /** False when the adapter has no usable CRS/affine: render in pixel space. */
  georeferenced: boolean;
  georefReason: GeorefReason | null;
  /** Ordered band names the file declares; null when it declares none. */
  bandNames: string[] | null;
  bandSchemaDeclared: boolean;
  sensor: string | null;
  patchGrid: {
    patchSize: number;
    stride: number;
    rows: number;
    cols: number;
    totalPatches: number;
  } | null;
}

export interface SceneView {
  id: string;
  projectId: string;
  acquisitionDateTime: string | null;
  sensor: 'Sentinel-1' | 'Sentinel-2';
  platform: string | null;
  productType: string | null;
  productLevel: string | null;
  processingBaseline: string | null;
  sourceFilename: string;
  crs: string | null;
  transform: number[] | null;
  width: number;
  height: number;
  bandCount: number;
  bandNames: (string | null)[] | null;
  bandDtypes: string[] | null;
  nodataValues: (number | null)[] | null;
  hasValidityMask: boolean;
  bounds: Bounds | null;
  pixelSizeX: number | null;
  pixelSizeY: number | null;
  polarization: string[] | null;
  acquisitionMode: string | null;
  orbitDirection: string | null;
  relativeOrbit: number | null;
  nativeBandResolutions: Record<string, number> | null;
  sizeBytes: number;
  registeredAt: string;
}

export interface LabelView {
  id: string;
  sampleId: string;
  sampleType: string;
  datasetId: string | null;
  className: string;
  geometry: { type: 'Point' | 'Polygon'; coordinates: unknown };
  coordinateSpace: 'pixel' | 'map';
  version: number;
  iteration: number;
  /** WGS84 anchor for the map, when the label can be projected. */
  center: [number, number] | null;
  createdAt: string;
}

export interface ClassMetric {
  className: string;
  support: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  iou: number | null;
}

export interface MetricsView {
  id: string;
  iteration: number;
  modelType: string;
  resolution: string;
  evaluation: string;
  evaluationDetails: string | null;
  evaluationStrategy: string | null;
  nSamples: number;
  nTrain: number | null;
  nTest: number | null;
  heldOutGroups: number | null;
  accuracy: number;
  f1Macro: number;
  f1Weighted: number;
  classes: string[];
  confusionMatrix: number[][];
  perClass: ClassMetric[];
  /** True when the engine could not compute a held-out score. */
  insufficient: boolean;
  createdAt: string;
}

export interface RunView {
  id: string;
  iteration: number;
  modelType: string;
  resolution: string;
  nSamples: number;
  checkpoint: string;
  createdAt: string;
  metrics: MetricsView;
}

export interface QuerySampleView {
  sampleId: string;
  datasetId: string;
  row: number;
  col: number;
  center: [number, number];
  window: PixelWindow;
  /** Centre in the dataset CRS, when the grid is georeferenced. */
  geo: [number, number] | null;
  bbox: Bounds | null;
  prediction: string | null;
  confidence: number | null;
  uncertainty: number | null;
}

export interface QueryBatchView {
  strategy: string;
  method: string | null;
  modelIteration: number | null;
  notes: string[];
  requestedAt: string;
  samples: QuerySampleView[];
}

export interface MapFieldView {
  layer: 'hard' | 'uncertainty';
  method: string | null;
  datasetId: string;
  iteration: number;
  trainingRunId: string;
  classes: string[];
  resolution: 'pixel' | 'patch';
  grid: {
    rows: number;
    cols: number;
    patchSize: number;
    stride: number;
    region: PixelWindow;
  };
  values: (number | null)[][];
  valid: boolean[][];
  min: number;
  max: number;
  stale: boolean;
  /** True only when the reference raster provably carries the model's bands. */
  bandSchemaVerified: boolean;
  bandSchemaReason: string | null;
  studyAreaApplied: boolean;
  studyAreaNote: string | null;
}

export interface LabelImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

export interface AdapterErrorShape {
  message: string;
  status: number;
}
