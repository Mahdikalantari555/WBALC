/**
 * RSAL -> view-model translation.
 *
 * Every function here is pure shaping: no fetches, no caching, no fabrication.
 * Values RSAL does not provide stay `null` so the UI can render an honest empty
 * state instead of an invented number.
 */
import { assessGeoreferencing, datasetBounds, normalizeCrs, toWgs84 } from '$lib/geo';
import type {
  BinaryView,
  ClassMetric,
  DatasetView,
  LabelView,
  MapFieldView,
  MetricsView,
  ProjectView,
  QueryBatchView,
  QueryDecision,
  QueryHistoryEntry,
  QueryItemView,
  QuerySampleView,
  RunView,
  SceneView,
} from '$lib/types';
import type {
  RsalBinarySummary,
  RsalDataset,
  RsalLabel,
  RsalMapField,
  RsalMetrics,
  RsalProject,
  RsalQueryBatch,
  RsalQueryItem,
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
      labelAliases: project.classification_config?.label_aliases ?? {},
    },
    taxonomy: project.taxonomy
      ? {
          version: project.taxonomy.version ?? null,
          // A snapshot written by this engine says where it came from; anything
          // else is reported as a project-configured list, never as a default.
          source:
            project.taxonomy.source === 'default'
              ? 'default'
              : project.taxonomy.source === 'project'
                ? 'project'
                : 'legacy',
          classes: project.taxonomy.classes ?? project.classes,
          displayNames: project.taxonomy.display_names ?? {},
          aliases: project.taxonomy.aliases ?? {},
        }
      : null,
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
    // Provenance is read, not derived: a label counts as query-answered only
    // when the engine stored that link.
    provenance: label.provenance === 'query' ? 'query' : 'manual',
    submittedClassName: label.submitted_class_name ?? null,
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
    batchId: response.batch_id != null ? String(response.batch_id) : null,
    strategy: response.strategy,
    method: response.method,
    strategyVersion: response.strategy_version ?? null,
    seed: response.seed ?? null,
    requestedSize: response.requested_size ?? null,
    modelIteration: response.model_iteration,
    trainingRunId: response.training_run_id != null ? String(response.training_run_id) : null,
    notes: response.notes ?? [],
    requestedAt: response.created_at ?? new Date().toISOString(),
    pool: response.pool
      ? {
          size: response.pool.size,
          hash: response.pool.hash,
          patchSize: response.pool.patch_size,
          stride: response.pool.stride,
          grid: response.pool.grid,
          gridCells: response.pool.grid_cells,
          labeledPatches: response.pool.n_labeled_patches,
          excludeLabeled: response.pool.exclude_labeled,
          eligibility: response.pool.eligibility,
        }
      : null,
    samples,
  };
}

/** Shape one durable query item (a selected sample plus its decision). */
export function toQueryItem(item: RsalQueryItem): QueryItemView {
  return {
    id: String(item.id),
    position: item.position,
    sampleId: item.sample_id,
    datasetId: String(item.dataset_id),
    row: item.row,
    col: item.col,
    center: [item.coords.center_x, item.coords.center_y],
    window: { x0: item.coords.x0, y0: item.coords.y0, x1: item.coords.x1, y1: item.coords.y1 },
    geo: item.geo_coords?.center
      ? [Number(item.geo_coords.center[0]), Number(item.geo_coords.center[1])]
      : null,
    bbox: item.geo_coords?.bbox
      ? ([...item.geo_coords.bbox].slice(0, 4) as [number, number, number, number])
      : null,
    score: item.score ?? null,
    uncertainty: item.uncertainty ?? null,
    prediction: item.prediction,
    confidence: item.confidence,
    status: item.status,
    decidedClass: item.decided_class ?? null,
    decidedAt: item.decided_at ?? null,
    decisionNote: item.decision_note ?? null,
    labelId: item.label_id != null ? String(item.label_id) : null,
  };
}

/** Shape a reopened batch, keeping server order and recorded decisions. */
export function toQueryHistory(batch: RsalQueryBatch): QueryHistoryEntry {
  const decisions: Record<QueryDecision, number> = {
    pending: 0,
    labeled: 0,
    rejected: 0,
    deferred: 0,
  };
  for (const [key, value] of Object.entries(batch.decisions ?? {})) {
    if (key in decisions) decisions[key as QueryDecision] = Number(value);
  }
  return {
    batchId: String(batch.id),
    strategy: batch.strategy,
    method: batch.method,
    strategyVersion: batch.strategy_version,
    seed: batch.seed,
    requested: batch.batch_size_requested,
    returned: batch.batch_size_returned,
    poolSize: batch.pool?.size ?? null,
    poolHash: batch.pool?.hash ?? null,
    modelIteration: batch.model_iteration,
    trainingRunId: batch.training_run_id != null ? String(batch.training_run_id) : null,
    datasetId: batch.dataset_id != null ? String(batch.dataset_id) : null,
    note: batch.note,
    notes: batch.notes ?? [],
    createdAt: batch.created_at,
    decisions,
    items: (batch.items ?? []).map(toQueryItem),
  };
}

/** Shape the derived-binary summary, or null when the run recorded none. */
export function toBinary(
  binary: RsalBinarySummary | null | undefined,
): BinaryView | null {
  if (!binary) return null;
  return {
    interpretation: binary.interpretation,
    version: binary.version,
    available: Boolean(binary.available),
    mapping: binary.mapping ?? {},
    sourceClasses: binary.source_classes ?? [],
    missingClasses: binary.missing_classes ?? [],
    reason: binary.reason ?? null,
    taxonomyVersion: binary.taxonomy_version ?? null,
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
    binary: toBinary(field.binary),
    // An older engine omits these; "unverified" is the honest default because
    // the adapter cannot claim a schema match the engine never reported.
    bandSchemaVerified: Boolean(field.band_schema_verified),
    bandSchemaReason: field.band_schema_reason ?? null,
    studyAreaApplied: Boolean(field.study_area_applied),
    studyAreaNote: field.study_area_note ?? null,
  };
}
