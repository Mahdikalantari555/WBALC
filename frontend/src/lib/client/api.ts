/**
 * Browser -> adapter client.
 *
 * Every call goes to a same-origin `/api/**` route handler; none of these
 * functions knows the RSAL URL. Errors are normalised to `ClientError` so the UI
 * can show the engine's own message (for example "strategy 'uncertainty'
 * requires a trained model").
 */
import type {
  DatasetView,
  LabelImportResult,
  LabelView,
  MapFieldView,
  ProjectView,
  QueryBatchView,
  QueryHistoryEntry,
  ComparisonView,
  ExperimentView,
  QueryItemView,
  RunLineageView,
  RunView,
  SceneAnalysisView,
  SceneView,
  FusionView,
  TemporalComparisonView,
  TemporalSeriesView,
  ProtocolView,
  EvaluationResultView,
  ReferenceAreaView,
  ResearchPlanView,
  PlanComparisonView,
  ReportView,
  ScientificStatusView,
} from '$lib/types';

export class ClientError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = 'ClientError';
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { accept: 'application/json', ...(init?.headers ?? {}) } });
  } catch {
    throw new ClientError('The adapter is unreachable. Is the app still running?', 0);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      data && typeof data === 'object' && 'message' in data
        ? String((data as { message: unknown }).message)
        : `Request failed (${response.status}).`;
    throw new ClientError(message, response.status);
  }
  return data as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<{ adapter: boolean; engine: boolean; detail: string }>('/api/health'),

  projects: () => request<ProjectView[]>('/api/projects'),
  createProject: (body: {
    name: string; description: string; classes?: string[]; generic_classes?: boolean;
    study_area_geometry?: Record<string, unknown>; study_area_crs?: string;
  }) =>
    request<ProjectView>('/api/projects', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    }),
  uploadDataset: (id: string, body: FormData) =>
    request<DatasetView>(`/api/projects/${enc(id)}/datasets`, { method: 'POST', body }),
  appendClass: (id: string, name: string) => request<ProjectView>(`/api/projects/${enc(id)}/classes`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }),
  }),
  uploadStack: (id: string, body: FormData) =>
    request<{ id: number }>(`/api/projects/${enc(id)}/raster-stack`, { method: 'POST', body }),
  registerScene: (id: string, body: FormData) =>
    request<SceneView>(`/api/projects/${enc(id)}/scenes`, { method: 'POST', body }),
  researchPathUrl: (id: string, format: 'json' | 'csv') =>
    `/api/projects/${enc(id)}/research-path?format=${format}`,
  project: (id: string) => request<ProjectView>(`/api/projects/${enc(id)}`),

  datasets: (id: string) => request<DatasetView[]>(`/api/projects/${enc(id)}/datasets`),
  scenes: (id: string) => request<SceneView[]>(`/api/projects/${enc(id)}/scenes`),
  labels: (id: string) => request<LabelView[]>(`/api/projects/${enc(id)}/labels`),
  runs: (id: string) => request<RunView[]>(`/api/projects/${enc(id)}/runs`),

  mapField: (
    id: string,
    options: {
      layer: 'hard' | 'uncertainty' | 'binary';
      method: string;
      datasetId: string;
      /** Records an explicit "I accept an unverified band schema" override. */
      acceptUnverifiedSchema?: boolean;
    },
  ) => {
    const query = new URLSearchParams({
      layer: options.layer,
      method: options.method,
      dataset: options.datasetId,
    });
    if (options.acceptUnverifiedSchema) query.set('accept_unverified_schema', 'true');
    return request<MapFieldView>(`/api/projects/${enc(id)}/map-field?${query.toString()}`);
  },

  query: (
    id: string,
    body: {
      strategy: string;
      method?: string;
      batchSize?: number;
      datasetId?: string;
      seed?: number | null;
      note?: string | null;
    },
  ) =>
    request<QueryBatchView>(`/api/projects/${enc(id)}/query`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  submitLabel: (
    id: string,
    body: {
      sampleId: string;
      datasetId: string;
      className: string;
      col: number;
      row: number;
      iteration?: number;
      revise?: boolean;
      queryBatchId?: string | null;
      queryItemId?: string | null;
    },
  ) =>
    request<LabelView>(`/api/projects/${enc(id)}/labels`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /** Reproducibility record of one run (manifest, artifact, what is missing). */
  runLineage: (id: string, runId: string) =>
    request<RunLineageView>(`/api/projects/${enc(id)}/runs/${enc(runId)}/lineage`),

  /** Compare runs (`runIds` empty = the whole project), saying where they differ. */
  compareRuns: (id: string, runIds: string[] = []) =>
    request<ComparisonView>(
      `/api/projects/${enc(id)}/compare${runIds.length ? `?runs=${enc(runIds.join(','))}` : ''}`,
    ),

  experiments: (id: string) => request<ExperimentView[]>(`/api/projects/${enc(id)}/experiments`),

  createExperiment: (
    id: string,
    body: { name: string; description?: string; hypothesis?: string | null; runIds?: string[] },
  ) =>
    request<ExperimentView>(`/api/projects/${enc(id)}/experiments`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  addRunsToExperiment: (id: string, experimentId: string, runIds: string[]) =>
    request<ExperimentView>(`/api/projects/${enc(id)}/experiments/${enc(experimentId)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ addRunIds: runIds }),
    }),

  removeRunFromExperiment: (id: string, experimentId: string, runId: string) =>
    request<ExperimentView>(`/api/projects/${enc(id)}/experiments/${enc(experimentId)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ removeRunId: runId }),
    }),

  /** Durable sampling history (newest first). Items are fetched per batch. */
  queryHistory: (id: string, limit = 25) =>
    request<QueryHistoryEntry[]>(`/api/projects/${enc(id)}/queries?limit=${limit}`),

  queryBatch: (id: string, batchId: string) =>
    request<QueryHistoryEntry>(`/api/projects/${enc(id)}/queries/${enc(batchId)}`),

  decideQueryItem: (
    id: string,
    batchId: string,
    itemId: string,
    body: {
      status: 'pending' | 'labeled' | 'rejected' | 'deferred';
      className?: string | null;
      note?: string | null;
    },
  ) =>
    request<QueryItemView>(`/api/projects/${enc(id)}/queries/${enc(batchId)}/items/${enc(itemId)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  train: (
    id: string,
    body: {
      resolution: 'patch' | 'pixel';
      evaluationStrategy: 'random' | 'spatial';
      modelType?: 'rf' | 'lightgbm';
      iteration?: number | null;
      /** Records an explicit override when the rasters' bands are unnamed. */
      acceptUnverifiedSchema?: boolean;
    },
  ) =>
    request<RunView>(`/api/projects/${enc(id)}/train`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  deleteLabel: (id: string, sampleId: string) =>
    request<void>(`/api/projects/${enc(id)}/labels/${enc(sampleId)}`, { method: 'DELETE' }),

  importLabels: (
    id: string,
    body: {
      geojson: unknown;
      classProperty?: string;
      datasetId?: string | null;
      mapping?: Record<string, string>;
      coordinateCrs?: 'EPSG:4326' | 'dataset';
    },
  ) =>
    request<LabelImportResult>(`/api/projects/${enc(id)}/labels/import`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /* ------------------------------------------- scene results & temporal (Phase 4) */

  /** Classify one scene on its own grid; the engine records an immutable analysis. */
  classifyScene: (
    id: string,
    sceneId: string,
    body: { method?: string; acceptUnverifiedSchema?: boolean } = {},
  ) =>
    request<SceneAnalysisView>(`/api/projects/${enc(id)}/scenes/${enc(sceneId)}/classify`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  sceneAnalyses: (id: string, sceneId: string) =>
    request<SceneAnalysisView[]>(`/api/projects/${enc(id)}/scenes/${enc(sceneId)}/analyses`),

  /** Per-date class/water areas from each scene's latest analysis (native grids). */
  temporalSeries: (id: string) =>
    request<TemporalSeriesView>(`/api/projects/${enc(id)}/temporal/series`),

  /**
   * Class transitions between two dates. Throws `ClientError` with the engine's
   * grid-mismatch message when the grids differ and no reference is given.
   */
  compareDates: (
    id: string,
    body: { beforeSceneId: string; afterSceneId: string; referenceSceneId?: string | null },
  ) =>
    request<TemporalComparisonView>(`/api/projects/${enc(id)}/temporal/compare`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  fusions: (id: string) => request<FusionView[]>(`/api/projects/${enc(id)}/fusion`),

  /** Late fusion of derived per-sensor products on an explicit target grid. */
  createFusion: (
    id: string,
    body: {
      name?: string;
      rule: 'weighted_probability' | 'weighted_vote' | 'priority';
      targetSceneId: string;
      analysisIds: string[];
      weights?: Record<string, number>;
      missingPolicy?: 'require_all' | 'renormalise';
      priority?: string[];
    },
  ) =>
    request<FusionView>(`/api/projects/${enc(id)}/fusion`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /* ------------------------------------------ research evaluation (Phase 5) */

  protocols: (id: string) =>
    request<ProtocolView[]>(`/api/projects/${enc(id)}/research/protocols`),

  createProtocol: (
    id: string,
    body: {
      name?: string;
      protocol: 'random' | 'spatial' | 'temporal';
      seed?: number;
      testSize?: number;
      blockSize?: number;
      buffer?: number;
    },
  ) =>
    request<ProtocolView>(`/api/projects/${enc(id)}/research/protocols`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  evaluations: (id: string) =>
    request<EvaluationResultView[]>(`/api/projects/${enc(id)}/research/evaluations`),

  /** Scores a protocol's held-out partition; the engine refits, it never reuses the production model. */
  evaluate: (id: string, body: { protocolId: string; modelType?: 'rf' | 'lightgbm'; resolution?: 'patch' | 'pixel' }) =>
    request<EvaluationResultView>(`/api/projects/${enc(id)}/research/evaluations`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  referenceAreas: (id: string) =>
    request<ReferenceAreaView[]>(`/api/projects/${enc(id)}/research/reference-areas`),

  addReferenceArea: (
    id: string,
    body: {
      sceneId?: string | null;
      label?: string;
      waterAreaM2: number;
      source: string;
      method: string;
      uncertaintyM2?: number | null;
    },
  ) =>
    request<ReferenceAreaView>(`/api/projects/${enc(id)}/research/reference-areas`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  researchPlans: (id: string) =>
    request<ResearchPlanView[]>(`/api/projects/${enc(id)}/research/plans`),

  createResearchPlan: (
    id: string,
    body: { name: string; hypothesis?: string | null; comparisonMetric?: string; repetitions?: number },
  ) =>
    request<ResearchPlanView>(`/api/projects/${enc(id)}/research/plans`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  comparePlan: (id: string, body: { planId: string; resultIds?: string[] }) =>
    request<PlanComparisonView>(`/api/projects/${enc(id)}/research/plans/compare`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  reports: (id: string) => request<ReportView[]>(`/api/projects/${enc(id)}/research/reports`),

  createReport: (id: string, body: { title?: string } = {}) =>
    request<ReportView>(`/api/projects/${enc(id)}/research/reports`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),

  scientificStatus: (id: string) =>
    request<ScientificStatusView>(`/api/projects/${enc(id)}/research/status`),

  /** Download URL (not fetched): a checksum-verified report artifact. */
  reportUrl: (id: string, reportId: string, kind: 'json' | 'csv' | 'markdown') =>
    `/api/projects/${enc(id)}/research/reports/${enc(reportId)}/files/${enc(kind)}`,

  /** Download URL (not fetched): a scene product the engine verified. */
  sceneExportUrl: (id: string, analysisId: string, kind: 'hard' | 'probability' | 'uncertainty') =>
    `/api/projects/${enc(id)}/analyses/${enc(analysisId)}/exports/${enc(kind)}`,

  /** Download URL (not fetched): the browser saves the engine's GeoTIFF. */
  exportUrl: (
    id: string,
    options: {
      type: 'hard' | 'probability' | 'uncertainty' | 'binary' | 'binary_probability';
      datasetId?: string;
      method?: string;
      acceptUnverifiedSchema?: boolean;
    },
  ) => {
    const query = new URLSearchParams({ type: options.type });
    if (options.datasetId) query.set('dataset', options.datasetId);
    if (options.method) query.set('method', options.method);
    if (options.acceptUnverifiedSchema) query.set('accept_unverified_schema', 'true');
    return `/api/projects/${enc(id)}/exports?${query.toString()}`;
  },
};
