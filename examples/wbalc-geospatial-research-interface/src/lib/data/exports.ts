import { classKeys, classes, evaluateModel, pct, type ErrorSite, type Model, type Observation, type Reviews, type XY } from './research';
import { boundary, mockReedOutlines, mockWaterOutline, sceneToLonLat } from './scene';

export function download(filename: string, mime: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

type Properties = Record<string, string | number | boolean>;

export function pointFeature<T extends Properties>(point: XY, properties: T) {
  return { type: 'Feature', geometry: { type: 'Point', coordinates: sceneToLonLat(point) }, properties: { ...properties, simulated: true } };
}

function polygonFeature<T extends Properties>(points: XY[], properties: T) {
  const coordinates = points.map(sceneToLonLat);
  const signedArea = coordinates.reduce((sum, [x, y], i) => {
    const [nx, ny] = coordinates[(i + 1) % coordinates.length];
    return sum + x * ny - y * nx;
  }, 0);
  if (signedArea < 0) coordinates.reverse();
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[...coordinates, coordinates[0]]] }, properties: { ...properties, simulated: true } };
}

export type ExportFeature = ReturnType<typeof polygonFeature> | ReturnType<typeof pointFeature>;

export function classificationFeatures(observation: Observation, model?: Model) {
  const source = { date: observation.date, sensor: observation.sensor, model: model?.name ?? 'Sentinel Fusion RF' };
  return [
    polygonFeature(mockWaterOutline(observation, model), { ...source, class: classes.water.name, nominal_area_km2: observation.water }),
    ...mockReedOutlines(observation, model).map(points => polygonFeature(points, { ...source, class: classes.vegetation.name })),
  ];
}

export const studyAreaFeature = () => polygonFeature(boundary, { name: 'Zarivar Lake study area', id: 'ZL-001' });

export function errorFeatures(sites: ErrorSite[], model: Model, date: string) {
  return sites.map(site => pointFeature(site.point, { id: site.id, model: model.name, date, observed_class: classes[site.actual].name, predicted_class: classes[site.predicted].name, source: 'simulated illustrative error site' }));
}

export const geojson = (features: ExportFeature[]) => JSON.stringify({
  type: 'FeatureCollection', name: 'WBALC Zarivar Lake demo', simulated: true,
  note: 'Schematic geometry. Not observed or surveyed data.', features,
}, null, 2);

export function evaluationCsv(model: Model, filter: 'all' | typeof classKeys[number], reviews: Reviews) {
  const metrics = evaluateModel(model);
  const escape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
  const rows = metrics.rows.filter(row => filter === 'all' || row.key === filter);
  return [
    ['project', 'model', 'class', 'support', 'overall_accuracy_pct', 'precision_pct', 'recall_pct', 'f1_pct', 'iou_pct', 'inference_seconds', 'local_review_count', 'simulated'],
    ...rows.map(row => ['ZL-001', model.name, classes[row.key].name, row.support, pct(metrics.accuracy).slice(0, -1), pct(row.precision).slice(0, -1), pct(row.recall).slice(0, -1), pct(row.f1).slice(0, -1), pct(row.iou).slice(0, -1), model.inference, Object.keys(reviews).length, 'true']),
  ].map(row => row.map(escape).join(',')).join('\r\n');
}