/**
 * RSAL -> view-model translation.
 *
 * Every function here is pure shaping: no fetches, no caching, no fabrication.
 * Values RSAL does not provide stay `null` so the UI can render an honest empty
 * state instead of an invented number.
 */
import { assessGeoreferencing, datasetBounds, normalizeCrs, toWgs84 } from '$lib/geo';
import type {
  ClassMetric,
  DatasetView,
  LabelView,
  MapFieldView,
  MetricsView,
  ProjectView,
  QueryBatchView,
  QuerySampleView,
  RunView,
  SceneView,
} from '$lib/types';
import type {
  RsalDataset,
  RsalLabel,
  RsalMapField,
  RsalMetrics,
  RsalProject,
  RsalQueryResponse,
  RsalScene,
  RsalTrainResponse,
} from './rsal';

export function toProject(project: RsalProject): ProjectView {
  return {
    id: String(project.id),
    name: project.name,
    description: project.description ?? '',
    status: project.status,
    classes: project.classes,
    classificationConfig: {
      internalClasses: project.classification_config?.internal_classes ?? project.classes,
      binaryOutputInterpretation:
        project.classification_config?.binary_output_interpretation ?? 'water_vs_non_water',
    },
    studyAreaGeometry: project.study_area_geometry ?? null,
    studyAreaCrs: project.study_area_crs ?? null,
    createdAt: project.created_at,
    updatedAt: project.updated_at,
  };
}

/** Geo context used by the shared geometry helpers. */
export function geoContext(dataset: RsalDataset) {
  return {
    crsCode: dataset.crs,
    transform: dataset.transform,
    width: dataset.width,
    height: dataset.height,
  };
}

export function toDataset(dataset: RsalDataset): DatasetView {
  const assessment = assessGeoreferencing(geoContext(dataset));
  return {
    id: String(dataset.id),
    projectId: String(dataset.project_id),
    name: dataset.filename,
    url: `/api/projects/${dataset.project_id}/datasets/${dataset.id}/file`,
    crs: normalizeCrs(dataset.crs),
    transform: dataset.transform,
    width: dataset.width,
    height: dataset.height,
    bands: dataset.bands,
    dtype: dataset.dtype,
    nodata: dataset.nodata,
    bounds: datasetBounds(geoContext(dataset)) ?? dataset.bounds,
    sizeBytes: dataset.size_bytes,
    createdAt: dataset.created_at,
    georeferenced: assessment.mode === 'map',
    georefReason: assessment.reason,
    bandNames: dataset.band_schema?.band_names ?? null,
    bandSchemaDeclared: Boolean(dataset.band_schema?.declared),
    sensor: dataset.band_schema?.sensor ?? null,
    patchGrid: dataset.patch_grid
      ? {
          patchSize: dataset.patch_grid.patch_size,
          stride: dataset.patch_grid.stride,
          rows: dataset.patch_grid.rows,
          cols: dataset.patch_grid.cols,
          totalPatches: dataset.patch_grid.total_patches,
        }
      : null,
  };
}

export function toScene(scene: RsalScene): SceneView {
  return {
    id: String(scene.id),
    projectId: String(scene.project_id),
    acquisitionDateTime: scene.acquisition_datetime,
    sensor: scene.sensor,
    platform: scene.platform,
    productType: scene.product_type,
    productLevel: scene.product_level,
    processingBaseline: scene.processing_baseline,
    sourceFilename: scene.source_filename,
    crs: normalizeCrs(scene.crs),
    transform: scene.transform,
    width: scene.width,
    height: scene.height,
    bandCount: scene.band_count,
    bandNames: scene.band_names ?? null,
    bandDtypes: scene.band_dtypes ?? null,
    nodataValues: scene.nodata_values ?? null,
    hasValidityMask: scene.has_validity_mask,
    bounds: scene.bounds,
    pixelSizeX: scene.pixel_size_x,
    pixelSizeY: scene.pixel_size_y,
    polarization: scene.polarization ?? null,
    acquisitionMode: scene.acquisition_mode,
    orbitDirection: scene.orbit_direction,
    relativeOrbit: scene.relative_orbit,
    nativeBandResolutions: scene.native_band_resolutions ?? null,
    sizeBytes: scene.size_bytes,
    registeredAt: scene.registered_at,
  };
}

/**
 * Project a stored label geometry to a WGS84 anchor.
 *
 * Labels are stored either in pixel space or in the dataset CRS. Anything the
 * adapter cannot project (no CRS, unsupported CRS) is reported as `null` — the
 * sample still exists in the table, it just has no map position.
 */
export function labelCenter(
  label: RsalLabel,
  datasets: Map<number, RsalDataset>,
): [number, number] | null {
  const dataset = label.dataset_id != null ? datasets.get(label.dataset_id) : undefined;
  if (!dataset?.transform) return null;
  const coordinates = label.geometry.coordinates as unknown;
  const first = label.geometry.type === 'Point' ? coordinates : (coordinates as number[][][])[0]?.[0];
  if (!first || !Array.isArray(first) || first.length < 2) return null;
  const x = Number(first[0]);
  const y = Number(first[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  let mapX = x;
  let mapY = y;
  if (label.coordinate_space === 'pixel') {
    const [a, b, c, d, e, f] = dataset.transform;
    mapX = a * x + b * y + c;
    mapY = d * x + e * y + f;
  }
  return toWgs84(geoContext(dataset), mapX, mapY);
}

export function toLabel(label: RsalLabel, datasets: Map<number, RsalDataset>): LabelView {
  return {
    id: String(label.id),
    sampleId: label.sample_id,
    sampleType: label.sample_type,
    datasetId: label.dataset_id != null ? String(label.dataset_id) : null,
    className: label.class_name,
    geometry: label.geometry,
    coordinateSpace: label.coordinate_space,
    version: label.version,
    iteration: label.iteration,
    center: labelCenter(label, datasets),
    createdAt: label.created_at,
  };
}

export function toClassMetrics(metrics: RsalMetrics): ClassMetric[] {
  const iou = metrics.per_class_iou ?? {};
  return (metrics.classes ?? []).map((className) => {
    const entry = metrics.per_class?.[className];
    return {
      className,
      support: entry?.support ?? 0,
      precision: finite(entry?.precision),
      recall: finite(entry?.recall),
      f1: finite(entry?.f1),
      iou: finite(iou[className]),
    };
  });
}

function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function toMetrics(metrics: RsalMetrics): MetricsView {
  return {
    id: String(metrics.id),
    iteration: metrics.iteration,
    modelType: metrics.model_type,
    resolution: metrics.resolution,
    evaluation: metrics.evaluation,
    evaluationDetails: metrics.evaluation_details ?? null,
    evaluationStrategy: metrics.evaluation_strategy ?? null,
    nSamples: metrics.n_samples,
    nTrain: metrics.n_train ?? null,
    nTest: metrics.n_test ?? null,
    heldOutGroups: metrics.held_out_groups ?? null,
    accuracy: metrics.accuracy,
    f1Macro: metrics.f1_macro,
    f1Weighted: metrics.f1_weighted,
    classes: metrics.classes ?? [],
    confusionMatrix: metrics.confusion_matrix ?? [],
    perClass: toClassMetrics(metrics),
    // The engine writes `insufficient_train_metrics` when it could not hold out
    // enough data; that is the only string we treat as "no honest score".
    insufficient: (metrics.evaluation ?? '').startsWith('insufficient_train'),
    createdAt: metrics.created_at,
  };
}

export function toRun(run: RsalTrainResponse): RunView {
  return {
    id: String(run.id),
    iteration: run.iteration,
    modelType: run.model_type,
    resolution: run.resolution,
    nSamples: run.n_samples,
    checkpoint: run.checkpoint,
    createdAt: run.metrics?.created_at ?? '',
    metrics: toMetrics(run.metrics),
  };
}

export function toQueryBatch(response: RsalQueryResponse): QueryBatchView {
  const samples: QuerySampleView[] = response.samples.map((sample) => ({
    sampleId: sample.sample_id,
    datasetId: String(sample.dataset_id),
    row: sample.coords.row,
    col: sample.coords.col,
    center: [sample.coords.center_x, sample.coords.center_y],
    window: {
      x0: sample.coords.x0,
      y0: sample.coords.y0,
      x1: sample.coords.x1,
      y1: sample.coords.y1,
    },
    geo: sample.geo_coords?.center
      ? [Number(sample.geo_coords.center[0]), Number(sample.geo_coords.center[1])]
      : null,
    bbox: sample.geo_coords?.bbox
      ? ([...sample.geo_coords.bbox].slice(0, 4) as [number, number, number, number])
      : null,
    prediction: sample.prediction,
    confidence: sample.confidence,
    uncertainty: sample.uncertainty,
  }));
  return {
    strategy: response.strategy,
    method: response.method,
    modelIteration: response.model_iteration,
    notes: response.notes ?? [],
    requestedAt: new Date().toISOString(),
    samples,
  };
}

export function toMapField(field: RsalMapField): MapFieldView {
  return {
    layer: field.layer,
    method: field.method,
    datasetId: String(field.dataset_id),
    iteration: field.model_iteration,
    trainingRunId: String(field.training_run_id),
    classes: field.classes ?? [],
    resolution: field.resolution,
    grid: {
      rows: field.grid.rows,
      cols: field.grid.cols,
      patchSize: field.grid.patch_size,
      stride: field.grid.stride,
      region: field.grid.region,
    },
    values: field.values,
    valid: field.valid,
    min: field.min,
    max: field.max,
    stale: field.stale,
    // An older engine omits these; "unverified" is the honest default because
    // the adapter cannot claim a schema match the engine never reported.
    bandSchemaVerified: Boolean(field.band_schema_verified),
    bandSchemaReason: field.band_schema_reason ?? null,
    studyAreaApplied: Boolean(field.study_area_applied),
    studyAreaNote: field.study_area_note ?? null,
  };
}
