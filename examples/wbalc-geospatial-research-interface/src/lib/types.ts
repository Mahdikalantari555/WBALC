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
    labelAliases: Record<string, string[]>;
  };
  /** Null for a generic/legacy project that never opted into the water taxonomy. */
  taxonomy: TaxonomyView | null;
  studyAreaGeometry: Record<string, unknown> | null;
  studyAreaCrs: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TaxonomyView {
  version: string | null;
  source: 'default' | 'project' | 'legacy';
  classes: string[];
  displayNames: Record<string, string>;
  aliases: Record<string, string[]>;
}

/** Derived binary water interpretation of a three-class product. */
export interface BinaryView {
  interpretation: 'water_vs_non_water' | 'open_water_vs_other';
  version: string;
  available: boolean;
  /** class id -> 'water' | 'non_water' (only classes the model actually learned) */
  mapping: Record<string, string>;
  sourceClasses: string[];
  missingClasses: string[];
  reason: string | null;
  taxonomyVersion: string | null;
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
  /** Content hash recorded at upload; null for a legacy upload. */
  contentSha256: string | null;
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
  /** 'query' only when the engine recorded a query-item link; never inferred. */
  provenance: 'manual' | 'query';
  /** Content hash of the raster the label belongs to, when the engine recorded it. */
  contentHash?: string | null;
  /** Text the annotator submitted when it differed from the resolved class. */
  submittedClassName: string | null;
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

export type LineageStatus = 'legacy' | 'incomplete' | 'complete';

export interface RunView {
  id: string;
  iteration: number;
  modelType: string;
  resolution: string;
  nSamples: number;
  checkpoint: string;
  createdAt: string;
  metrics: MetricsView;
  /** Short hash of the reproducibility manifest; null for a legacy run. */
  manifestHash: string | null;
  /** legacy = predates manifests; incomplete = manifest names what it lacks. */
  lineageStatus: LineageStatus;
  experimentId: string | null;
  checkpointSha256: string | null;
}

export interface RunLineageView {
  runId: string;
  iteration: number;
  experimentId: string | null;
  status: LineageStatus;
  manifestHash: string | null;
  missing: string[];
  notes: string[];
  artifact: { verified: boolean; sha256: string | null; reason: string | null } | null;
  labelSnapshotHash: string | null;
  inputs: { datasetId: string; sha256: string | null }[];
  environment: { revision: string | null; python: string | null } | null;
  config: Record<string, unknown>;
}

export interface ComparisonRowView {
  runId: string;
  iteration: number;
  modelType: string;
  accuracy: number | null;
  f1Macro: number | null;
  nSamples: number;
  evaluation: string | null;
  status: LineageStatus;
  manifestHash: string | null;
  labelSnapshotHash: string | null;
  inputHashes: Record<string, string | null>;
  config: Record<string, unknown>;
  environmentRevision: string | null;
}

export interface ComparisonView {
  experimentId: string | null;
  runs: ComparisonRowView[];
  differences: Record<string, unknown[]>;
  comparable: boolean;
  caveats: string[];
}

export interface ExperimentView {
  id: string;
  name: string;
  description: string;
  hypothesis: string | null;
  runIds: string[];
  createdAt: string;
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
  /**
   * Durable identity of the selection. The server owns the queue; the browser
   * copy is a cache that can always be reloaded from here.
   */
  batchId: string | null;
  strategy: string;
  method: string | null;
  strategyVersion: string | null;
  seed: number | null;
  requestedSize: number | null;
  modelIteration: number | null;
  trainingRunId: string | null;
  notes: string[];
  requestedAt: string;
  pool: QueryPoolView | null;
  samples: QuerySampleView[];
}

/** The eligible candidate pool a batch sampled from. */
export interface QueryPoolView {
  size: number;
  hash: string;
  patchSize: number;
  stride: number;
  grid: { rows: number; cols: number };
  gridCells: number;
  labeledPatches: number;
  excludeLabeled: boolean;
  eligibility: string;
}

export type QueryDecision = 'pending' | 'labeled' | 'rejected' | 'deferred';

/** One selected sample in a durable batch, with its recorded decision. */
export interface QueryItemView {
  id: string;
  position: number;
  sampleId: string;
  datasetId: string;
  row: number;
  col: number;
  center: [number, number];
  window: PixelWindow;
  geo: [number, number] | null;
  bbox: Bounds | null;
  score: number | null;
  uncertainty: number | null;
  prediction: string | null;
  confidence: number | null;
  status: QueryDecision;
  decidedClass: string | null;
  decidedAt: string | null;
  decisionNote: string | null;
  labelId: string | null;
}

/** A batch reopened from the server: same identities, order and decisions. */
export interface QueryHistoryEntry {
  batchId: string;
  strategy: string;
  method: string | null;
  strategyVersion: string;
  seed: number | null;
  requested: number;
  returned: number;
  poolSize: number | null;
  poolHash: string | null;
  modelIteration: number | null;
  trainingRunId: string | null;
  datasetId: string | null;
  note: string | null;
  notes: string[];
  createdAt: string;
  decisions: Record<QueryDecision, number>;
  items: QueryItemView[];
}

export interface MapFieldView {
  layer: 'hard' | 'uncertainty' | 'binary';
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
  /** Derived water interpretation; null when the run recorded none. */
  binary: BinaryView | null;
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

/* ---------------------------------------------- scene results & temporal (Phase 4) */

/** How a pixel area was derived. `kind` is never guessed by the UI. */
export interface PixelAreaMethodView {
  kind: 'projected' | 'geographic' | 'unknown' | 'other';
  supported: boolean;
  unit: string | null;
  metresPerUnit: number | null;
  ellipsoid: string | null;
  pixelAreaM2: number | null;
  variesByRow: boolean | null;
  rowAreaMinM2: number | null;
  rowAreaMaxM2: number | null;
  reason: string | null;
  note: string | null;
}

export interface ClassAreaView {
  className: string;
  classIndex: number;
  validPixels: number;
  areaM2: number;
  areaHa: number;
  shareOfValid: number;
}

export interface WaterAreaView {
  waterClasses: string[];
  areaM2: number;
  areaHa: number;
  shareOfValid: number;
  validAreaM2: number;
}

export interface AreaSummaryView {
  available: boolean;
  reason: string | null;
  perClass: ClassAreaView[];
  validPixels: number;
  totalPixels: number;
  coverage: number;
  validAreaM2: number;
  validAreaHa: number;
  pixelAreaM2Mean: number;
  method: PixelAreaMethodView | null;
  water: WaterAreaView | null;
}

export interface SceneAnalysisView {
  id: string;
  sceneId: string;
  runId: string;
  resolution: string;
  method: string;
  classes: string[];
  crs: string | null;
  width: number | null;
  height: number | null;
  sensor: string | null;
  /** True when the analysis ran on the scene's own grid (always, in this engine). */
  nativeGrid: true;
  bandContractVerified: boolean;
  bandContractReason: string | null;
  studyAreaApplied: boolean;
  studyAreaRule: string | null;
  artifacts: Record<string, { name: string | null; sha256: string | null; sizeBytes: number | null }>;
  areas: AreaSummaryView;
  analysisDigest: string | null;
  createdAt: string;
}

export interface TemporalDateView {
  sceneId: string;
  analysisId: string;
  acquisitionDateTime: string | null;
  sensor: string | null;
  validAreaM2: number;
  coverage: number;
  perClass: ClassAreaView[];
  water: WaterAreaView | null;
}

export interface TemporalSeriesView {
  classes: string[];
  dates: TemporalDateView[];
  /** Always 'native': this engine reports per-date areas without resampling. */
  mode: 'native';
  gridsIdentical: boolean;
  caveats: string[];
}

export interface TransitionView {
  from: string;
  to: string;
  pixels: number;
  areaM2: number;
  areaHa: number;
}

export interface TemporalComparisonView {
  beforeSceneId: string;
  afterSceneId: string;
  classes: string[];
  /** False when no resampling was performed (identical grids). */
  aligned: boolean;
  alignmentMethod: string | null;
  referenceSceneId: string | null;
  jointValidPixels: number;
  jointValidAreaM2: number;
  changedPixels: number;
  changedAreaM2: number;
  changedAreaHa: number;
  transitions: { from: string; to: string; pixels: number; areaM2: number; areaHa: number }[];
  matrix: { from: string; to: string; pixels: number; areaM2: number }[];
  denominator: string;
  before: TemporalDateView | null;
  after: TemporalDateView | null;
  caveats: string[];
}

export interface FusionSourceView {
  analysisId: string;
  sceneId: string;
  sensor: string;
  weight: number;
  gridAligned: boolean;
  analysisDigest: string | null;
}

export interface FusionView {
  id: string;
  name: string;
  rule: string;
  weights: Record<string, number>;
  missingPolicy: string;
  aligned: boolean;
  alignedSources: string[];
  sources: FusionSourceView[];
  classes: string[];
  areas: AreaSummaryView | null;
  unanimousShare: number | null;
  fusedValidPixels: number | null;
  fusionDigest: string | null;
  createdAt: string;
}
