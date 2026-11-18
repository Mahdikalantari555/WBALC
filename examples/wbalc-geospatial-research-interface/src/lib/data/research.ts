export const project = {
  id: 'ZL-001', name: 'Zarivar Lake', location: 'Kurdistan, Iran',
  area: 56.32, archiveReviewed: 124,
} as const;

export const classes = {
  water: { name: 'Open Water', short: 'Water', color: '#4aa9ff', line: '#74caff' },
  vegetation: { name: 'Aquatic Vegetation', short: 'Vegetation', color: '#65d592', line: '#a1f2a6' },
  other: { name: 'Other / Non-water', short: 'Non-water', color: '#a4b0c2', line: '#cbd3de' },
  uncertain: { name: 'Uncertain / Needs Review', short: 'Uncertain', color: '#f3be67', line: '#f8d79e' },
} as const;

export type LabelClass = keyof typeof classes;
export type PredictionClass = Exclude<LabelClass, 'uncertain'>;
export const classKeys: PredictionClass[] = ['water', 'vegetation', 'other'];
export const labelKeys: LabelClass[] = [...classKeys, 'uncertain'];

export type Sensor = 'Sentinel-1' | 'Sentinel-2';
export type SensorFilter = Sensor | 'all';
export const sensorDetails = {
  'Sentinel-1': { product: 'Sentinel-1 GRD', mode: 'C-band SAR', bands: 'VV / VH', resolution: '10 m', platform: 'Sentinel-1A' },
  'Sentinel-2': { product: 'Sentinel-2 L2A', mode: 'Multispectral optical', bands: 'RGB / NIR / SWIR', resolution: '10 m', platform: 'Sentinel-2B' },
} as const;

export interface Observation {
  date: string;
  sensor: Sensor;
  water: number;
  vegetation: number;
  cloud: number | null;
  acquisition: string;
}

export const observations: Observation[] = [
  { date: '2024-10-16', sensor: 'Sentinel-2', water: 6.21, vegetation: 1.90, cloud: 2.8, acquisition: '07:40' },
  { date: '2024-11-02', sensor: 'Sentinel-1', water: 6.36, vegetation: 1.83, cloud: null, acquisition: '02:49' },
  { date: '2024-11-18', sensor: 'Sentinel-2', water: 6.55, vegetation: 1.75, cloud: 5.6, acquisition: '07:37' },
  { date: '2024-12-10', sensor: 'Sentinel-1', water: 6.91, vegetation: 1.69, cloud: null, acquisition: '15:08' },
  { date: '2024-12-29', sensor: 'Sentinel-2', water: 7.08, vegetation: 1.67, cloud: 1.7, acquisition: '07:41' },
  { date: '2025-01-13', sensor: 'Sentinel-1', water: 7.17, vegetation: 1.62, cloud: null, acquisition: '02:53' },
  { date: '2025-01-30', sensor: 'Sentinel-2', water: 7.34, vegetation: 1.57, cloud: 7.1, acquisition: '07:39' },
  { date: '2025-02-12', sensor: 'Sentinel-1', water: 7.22, vegetation: 1.66, cloud: null, acquisition: '15:11' },
  { date: '2025-02-26', sensor: 'Sentinel-2', water: 7.48, vegetation: 1.67, cloud: 3.3, acquisition: '07:42' },
  { date: '2025-03-10', sensor: 'Sentinel-1', water: 7.65, vegetation: 1.61, cloud: null, acquisition: '02:57' },
  { date: '2025-03-25', sensor: 'Sentinel-2', water: 7.71, vegetation: 1.51, cloud: 2.3, acquisition: '07:40' },
  { date: '2025-04-14', sensor: 'Sentinel-2', water: 7.84, vegetation: 1.48, cloud: 1.2, acquisition: '07:41' },
];

export const latest = observations[observations.length - 1];
export const getObservation = (date: string) => observations.find(item => item.date === date) ?? latest;
export const fmtDate = (date: string, year = true) => new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', year: year ? 'numeric' : undefined, timeZone: 'UTC',
}).format(new Date(date));

export type ModelId = 'fusion' | 'unet' | 'sar';
export interface Model {
  id: ModelId;
  name: string;
  type: string;
  version: string;
  inputs: string;
  config: string;
  inference: number;
  matrix: number[][];
  stability: number;
  agreement: number;
  extent: number;
}

export const models: Model[] = [
  { id: 'fusion', name: 'Sentinel Fusion RF', type: 'Random forest', version: 'RF-FUSE v2.1', inputs: 'S1 VV / VH + S2 optical indices',
    config: '300 trees; max depth 18', inference: 1.42, matrix: [[97, 3, 0], [4, 73, 3], [1, 3, 116]], stability: .947, agreement: .928, extent: 1 },
  { id: 'unet', name: 'Optical U-Net', type: 'Semantic segmentation', version: 'UNET-S2 v1.4', inputs: 'S2 RGB + NIR + SWIR',
    config: 'ResNet-34 encoder; 256 px patch', inference: 2.86, matrix: [[96, 3, 1], [8, 68, 4], [2, 6, 112]], stability: .905, agreement: .884, extent: 1.055 },
  { id: 'sar', name: 'SAR Threshold', type: 'Threshold baseline', version: 'SAR-TH v1.0', inputs: 'S1 VV backscatter',
    config: 'Fixed VV threshold; -17 dB', inference: .34, matrix: [[91, 7, 2], [13, 59, 8], [4, 9, 107]], stability: .831, agreement: .789, extent: .91 },
];

export const getModel = (id: ModelId) => models.find(model => model.id === id) ?? models[0];
export const metricKeys = ['precision', 'recall', 'f1', 'iou'] as const;
export const metricLabels = { precision: 'Precision', recall: 'Recall', f1: 'F1-score', iou: 'IoU' } as const;
export const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function evaluateModel(model: Model) {
  const support = model.matrix.map(row => row.reduce((total, count) => total + count, 0));
  const total = support.reduce((sum, count) => sum + count, 0);
  const rows = classKeys.map((key, i) => {
    const tp = model.matrix[i][i];
    const predicted = model.matrix.reduce((sum, row) => sum + row[i], 0);
    const precision = tp / predicted;
    const recall = tp / support[i];
    return { key, support: support[i], precision, recall, f1: 2 * precision * recall / (precision + recall), iou: tp / (support[i] + predicted - tp) };
  });
  return {
    rows, total,
    accuracy: model.matrix.reduce((sum, row, i) => sum + row[i], 0) / total,
    precision: rows.reduce((sum, row) => sum + row.precision, 0) / rows.length,
    recall: rows.reduce((sum, row) => sum + row.recall, 0) / rows.length,
    f1: rows.reduce((sum, row) => sum + row.f1, 0) / rows.length,
    iou: rows.reduce((sum, row) => sum + row.iou, 0) / rows.length,
  };
}

export type XY = readonly [number, number];
export interface Sample {
  id: string;
  point: XY;
  prediction: PredictionClass;
  uncertainty: number;
  location: string;
  observation: string;
}

export const samples: Sample[] = [
  { id: 'ZL-S014', point: [612, 445], prediction: 'vegetation', uncertainty: .87, location: 'Western reed margin', observation: '2025-04-14' },
  { id: 'ZL-S015', point: [794, 319], prediction: 'water', uncertainty: .81, location: 'Northeast shoreline', observation: '2025-04-14' },
  { id: 'ZL-S016', point: [791, 768], prediction: 'vegetation', uncertainty: .76, location: 'Southern marsh', observation: '2025-04-14' },
  { id: 'ZL-S017', point: [876, 590], prediction: 'other', uncertainty: .72, location: 'Eastern agricultural edge', observation: '2025-03-25' },
  { id: 'ZL-S018', point: [575, 160], prediction: 'water', uncertainty: .69, location: 'Northern inlet', observation: '2025-04-14' },
  { id: 'ZL-S019', point: [835, 504], prediction: 'vegetation', uncertainty: .65, location: 'East bank reeds', observation: '2025-04-14' },
  { id: 'ZL-S020', point: [888, 842], prediction: 'vegetation', uncertainty: .57, location: 'Southern outlet', observation: '2025-03-10' },
  { id: 'ZL-S021', point: [703, 646], prediction: 'water', uncertainty: .46, location: 'Southwest shoreline', observation: '2025-02-26' },
  { id: 'ZL-S022', point: [703, 381], prediction: 'water', uncertainty: .21, location: 'Central open water', observation: '2025-04-14' },
  { id: 'ZL-S023', point: [591, 270], prediction: 'vegetation', uncertainty: .61, location: 'Northwest reed margin', observation: '2025-04-14' },
  { id: 'ZL-S024', point: [966, 435], prediction: 'other', uncertainty: .34, location: 'East bank fields', observation: '2025-04-14' },
  { id: 'ZL-S025', point: [756, 578], prediction: 'water', uncertainty: .18, location: 'Southern open water', observation: '2025-02-12' },
];

export interface Review { label: LabelClass; date: string }
export type Reviews = Record<string, Review>;
export const seededReviews: Reviews = {
  'ZL-S022': { label: 'water', date: '2025-04-15' },
  'ZL-S023': { label: 'vegetation', date: '2025-04-15' },
  'ZL-S024': { label: 'other', date: '2025-04-15' },
  'ZL-S025': { label: 'water', date: '2025-04-15' },
};

export interface ErrorSite {
  id: string;
  point: XY;
  actual: PredictionClass;
  predicted: PredictionClass;
  models: ModelId[];
}

export const errorSites: ErrorSite[] = [
  { id: 'E01', point: [614, 450], actual: 'vegetation', predicted: 'water', models: ['fusion', 'unet', 'sar'] },
  { id: 'E02', point: [792, 323], actual: 'water', predicted: 'vegetation', models: ['fusion', 'sar'] },
  { id: 'E03', point: [815, 741], actual: 'vegetation', predicted: 'other', models: ['fusion', 'unet', 'sar'] },
  { id: 'E04', point: [874, 586], actual: 'other', predicted: 'vegetation', models: ['fusion', 'unet'] },
  { id: 'E05', point: [730, 664], actual: 'water', predicted: 'vegetation', models: ['unet', 'sar'] },
  { id: 'E06', point: [583, 178], actual: 'water', predicted: 'other', models: ['sar'] },
  { id: 'E07', point: [833, 486], actual: 'vegetation', predicted: 'water', models: ['unet', 'sar'] },
  { id: 'E08', point: [894, 833], actual: 'other', predicted: 'water', models: ['sar'] },
  { id: 'E09', point: [850, 368], actual: 'vegetation', predicted: 'other', models: ['sar'] },
];