/**
 * RSAL -> view-model translation.
 *
 * Every function here is pure shaping: no fetches, no caching, no fabrication.
 * Values RSAL does not provide stay `null` so the UI can render an honest empty
 * state instead of an invented number.
 */
import { assessGeoreferencing, datasetBounds, normalizeCrs, toWgs84 } from '$lib/geo';
import type {
  AreaSummaryView,
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
  ComparisonView,
  ExperimentView,
  QueryItemView,
  QuerySampleView,
  RunLineageView,
  RunView,
  SceneAnalysisView,
  SceneView,
  TemporalComparisonView,
  TemporalDateView,
  TemporalSeriesView,
  FusionView,
  ProtocolView,
  EvaluationResultView,
  ReferenceAreaView,
  ResearchPlanView,
  PlanComparisonView,
  ReportView,
  ScientificStatusView,
  NamedMetricValue,
} from '$lib/types';
import type {
  RsalBinarySummary,
  RsalDataset,
  RsalLabel,
  RsalMapField,
  RsalMetrics,
  RsalComparison,
  RsalExperiment,
  RsalProject,
  RsalQueryBatch,
  RsalQueryItem,
  RsalQueryResponse,
  RsalRunLineage,
  RsalRunSummary,
  RsalAreaSummary,
  RsalDateArea,
  RsalFusion,
  RsalScene,
  RsalSceneAnalysis,
  RsalTemporalComparison,
  RsalTemporalSeries,
  RsalProtocol,
  RsalEvaluationResult,
  RsalReferenceArea,
  RsalResearchPlan,
  RsalPlanComparison,
  RsalReport,
  RsalScientificStatus,
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
    origin: dataset.origin === 'scene' ? 'scene' : 'upload',
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
    // Only what the engine recorded: an older upload has no content identity and
    // must not be shown as if it did.
    contentSha256: dataset.content_sha256 ?? null,
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
    datasetId: scene.dataset_id != null ? String(scene.dataset_id) : null,
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

export function toRun(run: RsalTrainResponse | RsalRunSummary): RunView {
  const summary = run as RsalRunSummary;
  // A listed run carries its metrics inline; a fresh TrainResponse nests them.
  const metrics = 'metrics' in run ? run.metrics : (summary as unknown as RsalMetrics);
  return {
    id: String(run.id),
    iteration: run.iteration,
    modelType: run.model_type,
    resolution: run.resolution,
    nSamples: run.n_samples,
    checkpoint: 'checkpoint' in run ? run.checkpoint : '',
    createdAt: metrics?.created_at ?? '',
    metrics: toMetrics(metrics),
    // Lineage is reported, never assumed: a run without a manifest is 'legacy'.
    manifestHash: summary.manifest_hash ?? null,
    lineageStatus: summary.lineage_status ?? 'legacy',
    experimentId: summary.experiment_id != null ? String(summary.experiment_id) : null,
    checkpointSha256: summary.checkpoint_sha256 ?? null,
  };
}

/** Shape a run's lineage record, keeping "unavailable" distinguishable from "ok". */
export function toRunLineage(lineage: RsalRunLineage): RunLineageView {
  const manifest = (lineage.manifest ?? {}) as {
    labels?: { hash?: string };
    inputs?: { dataset_id?: number; content_sha256?: string | null }[];
    environment?: { revision?: string | null; python?: string | null };
    config?: Record<string, unknown>;
  };
  return {
    runId: String(lineage.run_id),
    iteration: lineage.iteration,
    experimentId: lineage.experiment_id != null ? String(lineage.experiment_id) : null,
    status: lineage.lineage_status,
    manifestHash: lineage.manifest_hash,
    missing: lineage.missing ?? [],
    notes: lineage.notes ?? [],
    artifact: lineage.artifact
      ? {
          verified: Boolean(lineage.artifact.verified),
          sha256: lineage.artifact.sha256 ?? null,
          reason: lineage.artifact.reason ?? null,
        }
      : null,
    labelSnapshotHash: manifest.labels?.hash ?? null,
    inputs: (manifest.inputs ?? []).map((entry) => ({
      datasetId: String(entry.dataset_id ?? ''),
      sha256: entry.content_sha256 ?? null,
    })),
    environment: manifest.environment
      ? {
          revision: manifest.environment.revision ?? null,
          python: manifest.environment.python ?? null,
        }
      : null,
    config: manifest.config ?? {},
  };
}

export function toComparison(comparison: RsalComparison): ComparisonView {
  return {
    experimentId: comparison.experiment_id != null ? String(comparison.experiment_id) : null,
    runs: comparison.runs.map((row) => ({
      runId: String(row.run_id),
      iteration: row.iteration,
      modelType: row.model_type,
      accuracy: row.accuracy ?? null,
      f1Macro: row.f1_macro ?? null,
      nSamples: row.n_samples,
      evaluation: row.evaluation ?? null,
      status: row.lineage_status,
      manifestHash: row.manifest_hash,
      labelSnapshotHash: row.label_snapshot_hash,
      inputHashes: row.input_hashes ?? {},
      config: row.config ?? {},
      environmentRevision: row.environment_revision,
    })),
    differences: comparison.differences ?? {},
    comparable: Boolean(comparison.comparable),
    caveats: comparison.caveats ?? [],
  };
}

export function toExperiment(experiment: RsalExperiment): ExperimentView {
  return {
    id: String(experiment.id),
    name: experiment.name,
    description: experiment.description ?? '',
    hypothesis: experiment.hypothesis ?? null,
    runIds: (experiment.run_ids ?? []).map(String),
    createdAt: experiment.created_at,
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
    samplesAdded: batch.samples_added ?? null,
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

/* ------------------------------------------- scene results & temporal (Phase 4) */

export function toPixelAreaMethod(
  method: RsalSceneAnalysis['areas']['method'],
): import('$lib/types').PixelAreaMethodView | null {
  if (!method) return null;
  return {
    kind: method.kind,
    supported: method.supported,
    unit: method.unit ?? null,
    metresPerUnit: method.metres_per_unit ?? null,
    ellipsoid: method.ellipsoid ?? null,
    pixelAreaM2: method.pixel_area_m2 ?? null,
    variesByRow: method.varies_by_row ?? null,
    rowAreaMinM2: method.row_area_min_m2 ?? null,
    rowAreaMaxM2: method.row_area_max_m2 ?? null,
    reason: method.reason ?? null,
    note: method.note ?? null,
  };
}

export function toAreaSummary(areas: RsalAreaSummary | null | undefined): AreaSummaryView {
  if (!areas) {
    return {
      available: false,
      reason: 'no area summary recorded for this product',
      perClass: [],
      validPixels: 0,
      totalPixels: 0,
      coverage: 0,
      validAreaM2: 0,
      validAreaHa: 0,
      pixelAreaM2Mean: 0,
      method: null,
      water: null,
    };
  }
  return {
    available: areas.available,
    reason: areas.reason ?? null,
    perClass: (areas.per_class ?? []).map((entry) => ({
      className: entry.class_name,
      classIndex: entry.class_index,
      validPixels: entry.valid_pixels,
      areaM2: entry.area_m2,
      areaHa: entry.area_ha,
      shareOfValid: entry.share_of_valid,
    })),
    validPixels: areas.valid_pixels,
    totalPixels: areas.total_pixels,
    coverage: areas.coverage,
    validAreaM2: areas.valid_area_m2,
    validAreaHa: areas.valid_area_ha,
    pixelAreaM2Mean: areas.pixel_area_m2_mean,
    method: toPixelAreaMethod(areas.method ?? null),
    water: areas.water
      ? {
          waterClasses: areas.water.water_classes,
          areaM2: areas.water.area_m2,
          areaHa: areas.water.area_ha,
          shareOfValid: areas.water.share_of_valid,
          validAreaM2: areas.water.valid_area_m2,
        }
      : null,
  };
}

export function toSceneAnalysis(analysis: RsalSceneAnalysis): SceneAnalysisView {
  return {
    id: String(analysis.id),
    sceneId: String(analysis.scene_id),
    runId: String(analysis.training_run_id),
    resolution: analysis.resolution,
    method: analysis.method,
    classes: analysis.classes ?? [],
    crs: normalizeCrs(analysis.grid?.crs ?? null),
    width: analysis.grid?.width ?? null,
    height: analysis.grid?.height ?? null,
    sensor: analysis.grid?.sensor ?? null,
    nativeGrid: true,
    bandContractVerified: Boolean(analysis.contract?.verified),
    bandContractReason: (analysis.contract?.reason as string | undefined) ?? null,
    studyAreaApplied: Boolean(analysis.study_area?.applied),
    studyAreaRule: (analysis.study_area?.rule as string | undefined) ?? null,
    artifacts: Object.fromEntries(
      Object.entries(analysis.artifacts ?? {}).map(([kind, entry]) => [
        kind,
        {
          name: entry.name ?? null,
          sha256: entry.sha256 ?? null,
          sizeBytes: entry.size_bytes ?? null,
        },
      ]),
    ),
    areas: toAreaSummary(analysis.areas),
    analysisDigest: (analysis.lineage?.analysis_digest as string | undefined) ?? null,
    createdAt: analysis.created_at,
  };
}

export function toTemporalDate(date: RsalDateArea): TemporalDateView {
  return {
    sceneId: String(date.scene_id),
    analysisId: String(date.analysis_id),
    acquisitionDateTime: date.acquisition_datetime,
    sensor: date.sensor ?? null,
    validAreaM2: date.valid_area_m2,
    coverage: date.coverage,
    perClass: (date.per_class ?? []).map((entry) => ({
      className: entry.class_name,
      classIndex: entry.class_index,
      validPixels: entry.valid_pixels,
      areaM2: entry.area_m2,
      areaHa: entry.area_ha,
      shareOfValid: entry.share_of_valid,
    })),
    water: date.water
      ? {
          waterClasses: date.water.water_classes,
          areaM2: date.water.area_m2,
          areaHa: date.water.area_ha,
          shareOfValid: date.water.share_of_valid,
          validAreaM2: date.water.valid_area_m2,
        }
      : null,
  };
}

export function toTemporalSeries(series: RsalTemporalSeries): TemporalSeriesView {
  return {
    classes: series.classes ?? [],
    dates: (series.dates ?? []).map(toTemporalDate),
    mode: 'native',
    gridsIdentical: Boolean(series.alignment?.grids_identical),
    caveats: series.caveats ?? [],
  };
}

export function toTemporalComparison(comparison: RsalTemporalComparison): TemporalComparisonView {
  const transitions = comparison.transitions;
  const classes = transitions.classes ?? comparison.classes ?? [];
  const matrix: { from: string; to: string; pixels: number; areaM2: number }[] = [];
  (transitions.matrix ?? []).forEach((row, rowIndex) => {
    row.forEach((pixels, colIndex) => {
      matrix.push({
        from: classes[rowIndex] ?? `#${rowIndex}`,
        to: classes[colIndex] ?? `#${colIndex}`,
        pixels,
        areaM2: transitions.matrix_area_m2?.[rowIndex]?.[colIndex] ?? 0,
      });
    });
  });
  return {
    beforeSceneId: String(comparison.before_scene_id),
    afterSceneId: String(comparison.after_scene_id),
    classes,
    aligned: Boolean(comparison.alignment?.aligned),
    alignmentMethod: (comparison.alignment?.method as string | undefined) ?? null,
    referenceSceneId:
      comparison.alignment?.reference_scene_id != null
        ? String(comparison.alignment.reference_scene_id)
        : null,
    jointValidPixels: transitions.joint_valid_pixels,
    jointValidAreaM2: transitions.joint_valid_area_m2,
    changedPixels: transitions.changed_pixels,
    changedAreaM2: transitions.changed_area_m2,
    changedAreaHa: transitions.changed_area_ha,
    transitions: (transitions.changes ?? []).map((entry) => ({
      from: entry.from ?? '',
      to: entry.to ?? '',
      pixels: entry.pixels,
      areaM2: entry.area_m2,
      areaHa: entry.area_ha,
    })),
    matrix,
    denominator: transitions.denominator,
    before: comparison.before ? toTemporalDate(comparison.before) : null,
    after: comparison.after ? toTemporalDate(comparison.after) : null,
    caveats: comparison.caveats ?? [],
  };
}

export function toFusion(fusion: RsalFusion): FusionView {
  const alignedSources = (fusion.sources ?? [])
    .filter((source) => source.grid_aligned)
    .map((source) => String(source.analysis_id));
  return {
    id: String(fusion.id),
    name: fusion.name,
    rule: fusion.rule,
    weights: fusion.weights ?? {},
    missingPolicy: fusion.missing_policy,
    aligned: alignedSources.length > 0,
    alignedSources,
    sources: (fusion.sources ?? []).map((source) => ({
      analysisId: String(source.analysis_id),
      sceneId: String(source.scene_id),
      sensor: source.sensor,
      weight: source.weight,
      gridAligned: source.grid_aligned,
      analysisDigest: source.analysis_digest ?? null,
    })),
    classes: fusion.classes ?? [],
    areas: fusion.areas ? toAreaSummary(fusion.areas) : null,
    unanimousShare:
      typeof fusion.agreement?.unanimous_share === 'number'
        ? (fusion.agreement.unanimous_share as number)
        : null,
    fusedValidPixels:
      typeof fusion.agreement?.fused_valid_pixels === 'number'
        ? (fusion.agreement.fused_valid_pixels as number)
        : null,
    fusionDigest: (fusion.lineage?.fusion_digest as string | undefined) ?? null,
    createdAt: fusion.created_at,
  };
}

/* -------------------------------------------- research evaluation (Phase 5) */

function namedMetric(value: unknown): NamedMetricValue | null {
  if (!value || typeof value !== 'object') return null;
  const entry = value as { value?: number | null; classes_used?: string[]; classes_skipped?: string[]; reason?: string | null };
  return {
    value: typeof entry.value === 'number' ? entry.value : null,
    classesUsed: entry.classes_used ?? [],
    classesSkipped: entry.classes_skipped ?? [],
    reason: entry.reason ?? null,
  };
}

export function toProtocol(protocol: RsalProtocol): ProtocolView {
  return {
    id: String(protocol.id),
    name: protocol.name,
    protocol: protocol.protocol,
    status: protocol.status,
    reason: protocol.reason,
    trainCount: protocol.train_count,
    testCount: protocol.test_count,
    heldOutGroups: protocol.held_out_groups ?? [],
    splitHash: protocol.split_hash,
    caveats: protocol.caveats ?? [],
    configuration: protocol.configuration ?? {},
    createdAt: protocol.created_at,
  };
}

export function toEvaluationResult(result: RsalEvaluationResult): EvaluationResultView {
  const metrics = result.metrics ?? {};
  const calibrationBlock = (result.calibration ?? {}) as Record<string, unknown>;
  const coverageBlock = (result.coverage ?? {}) as Record<string, unknown>;
  const macro: Record<string, NamedMetricValue> = {};
  for (const [key, value] of Object.entries(metrics.macro ?? {})) {
    const parsed = namedMetric(value);
    if (parsed) macro[key] = parsed;
  }
  return {
    id: String(result.id),
    protocolId: String(result.protocol_id),
    protocol: result.protocol,
    splitHash: result.split_hash,
    modelType: result.model_type,
    resolution: result.resolution,
    status: result.status,
    accuracy: typeof metrics.accuracy === 'number' ? metrics.accuracy : null,
    balancedAccuracy: namedMetric(metrics.balanced_accuracy),
    macro,
    classes: (metrics.per_class ?? []).map((row) => ({
      className: row.class_name,
      support: row.support,
      predicted: row.predicted,
      precision: row.precision,
      recall: row.recall,
      f1: row.f1,
      iou: row.iou,
      // Undefined metrics are reported with their reason, never as 1.0 or 0.0.
      undefined: row.undefined ?? {},
    })),
    nTrain: typeof metrics.n_train === 'number' ? metrics.n_train : null,
    nTest: typeof metrics.n_test === 'number' ? metrics.n_test : null,
    dropped: (metrics.dropped as Record<string, unknown> | undefined) ?? null,
    calibration: {
      available: Boolean(calibrationBlock.available),
      reason: (calibrationBlock.reason as string | undefined) ?? null,
      nSamples: typeof calibrationBlock.n_samples === 'number' ? (calibrationBlock.n_samples as number) : null,
      expectedCalibrationError:
        typeof calibrationBlock.expected_calibration_error === 'number'
          ? (calibrationBlock.expected_calibration_error as number)
          : null,
      maximumCalibrationError:
        typeof calibrationBlock.maximum_calibration_error === 'number'
          ? (calibrationBlock.maximum_calibration_error as number)
          : null,
      brierScore: typeof calibrationBlock.brier_score === 'number' ? (calibrationBlock.brier_score as number) : null,
      method: (calibrationBlock.method as string | undefined) ?? null,
      caveat: (calibrationBlock.caveat as string | undefined) ?? null,
    },
    coverage: {
      available: Boolean(coverageBlock.available),
      points: Array.isArray(coverageBlock.points)
        ? (coverageBlock.points as Record<string, unknown>[]).map((point) => ({
            threshold: Number(point.threshold ?? 0),
            retained: Number(point.retained ?? 0),
            coverage: Number(point.coverage ?? 0),
            accuracy: typeof point.accuracy === 'number' ? (point.accuracy as number) : null,
          }))
        : [],
      caveat: (coverageBlock.caveat as string | undefined) ?? null,
    },
    caveats: result.caveats ?? [],
    createdAt: result.created_at,
  };
}

export function toReferenceArea(area: RsalReferenceArea): ReferenceAreaView {
  return {
    id: String(area.id),
    sceneId: area.scene_id === null ? null : String(area.scene_id),
    label: area.label,
    waterAreaM2: area.water_area_m2,
    source: area.source,
    method: area.method,
    uncertaintyM2: area.uncertainty_m2,
    createdAt: area.created_at,
  };
}

export function toResearchPlan(plan: RsalResearchPlan): ResearchPlanView {
  return {
    id: String(plan.id),
    name: plan.name,
    hypothesis: plan.hypothesis,
    protocolId: plan.protocol_id === null ? null : String(plan.protocol_id),
    comparisonMetric: plan.comparison_metric,
    factors: plan.factors ?? [],
    repetitions: plan.repetitions,
    createdAt: plan.created_at,
  };
}

export function toPlanComparison(comparison: RsalPlanComparison): PlanComparisonView {
  return {
    planId: String(comparison.plan_id),
    comparisonMetric: comparison.comparison_metric,
    results: (comparison.results ?? []).map((row) => ({
      resultId: String(row.result_id),
      modelType: row.model_type,
      resolution: row.resolution,
      status: row.status,
      value: row.value,
      nTest: row.n_test,
    })),
    shared: comparison.shared ?? {},
    differing: comparison.differing ?? {},
    paired: comparison.paired,
    caveats: comparison.caveats ?? [],
  };
}

export function toReport(report: RsalReport): ReportView {
  return {
    id: String(report.id),
    title: report.title,
    status: report.status,
    digest: report.digest,
    artifacts: Object.fromEntries(
      Object.entries(report.artifacts ?? {}).map(([kind, entry]) => [
        kind,
        {
          name: entry.name,
          sha256: entry.sha256,
          sizeBytes: entry.size_bytes,
          mediaType: entry.media_type,
        },
      ]),
    ),
    caveats: report.caveats ?? [],
    scientificStatus: {
      softwareValidation: report.scientific_status?.software_validation ?? 'unknown',
      scientificValidity: report.scientific_status?.scientific_validity ?? 'unknown',
      detail: report.scientific_status?.detail ?? '',
    },
    createdAt: report.created_at,
  };
}

export function toScientificStatus(status: RsalScientificStatus): ScientificStatusView {
  return {
    softwareValidation: status.software_validation,
    scientificValidity: status.scientific_validity,
    detail: status.detail,
    protocols: status.protocols,
    results: status.results,
    referenceAreas: status.reference_areas,
    reports: status.reports,
  };
}
