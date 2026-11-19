/**
 * TerraLab API routes, backed exclusively by the RSAL FastAPI service.
 * This adapter translates between the browser-facing shapes in @/types and
 * the RSAL contract (projects / dataset / labels / query / train / metrics).
 */
import { NextRequest, NextResponse } from 'next/server';
import type {
  Bounds,
  Dataset,
  Iteration,
  LabelInput,
  Metrics,
  Project,
  Sample,
  SomClassification,
  SomData,
} from '@/types';
import { classesFromNames, CLASS_COLORS } from '@/lib/palette';
import {
  ApiError,
  rsalFetch,
  rsalGet,
  rsalGetOptional,
  rsalPost,
  type RsalDataset,
  type RsalLabel,
  type RsalMetrics,
  type RsalProject,
  type RsalQueryResponse,
  type RsalSomClassifyResponse,
  type RsalSomResponse,
  type RsalTrainResponse,
} from './rsal';
import { sampleResolutionField, trainBody } from './payloads';
import {
  applyAffine,
  assessGeoreferencing,
  datasetBounds,
  displayToPixel,
  geoContext,
  isGeoreferenced,
  labelPixelWindow,
  labelToDisplay,
  pixelRectToDisplay,
  pixelToDisplay,
} from './geo';

type Context = { params: Promise<{ id?: string; action?: string; itemId?: string }> };

const pid = (id: string) => {
  if (!/^\d+$/.test(id)) throw new ApiError('Project not found.', 404);
  return id;
};

// ------------------------------------------------------------- translations
function toIteration(m: RsalMetrics, previousSamples: number): Iteration {
  return {
    id: String(m.id),
    projectId: String(m.project_id),
    number: m.iteration,
    accuracy: m.accuracy,
    f1: m.f1_macro,
    sampleCount: Math.max(0, m.n_samples - previousSamples),
    labeledCount: m.n_samples,
    createdAt: m.created_at,
  };
}

function toDataset(d: RsalDataset): Dataset {
  const geoBounds = datasetBounds(d);
  const georef = assessGeoreferencing(geoContext(d));
  const res = d.transform
    ? `${Math.abs(d.transform[0]).toLocaleString('en', { maximumFractionDigits: 6 })} ${
        d.crs === 'EPSG:4326' ? '°' : 'm'
      }`
    : 'Unknown';
  return {
    id: String(d.id),
    projectId: String(d.project_id),
    name: d.filename,
    size: d.size_bytes,
    bands: d.bands,
    width: d.width,
    height: d.height,
    resolution: res,
    crs: d.crs ?? 'Not georeferenced',
    transform: d.transform,
    bounds: geoBounds ?? [0, 0, d.width, d.height],
    pixelSpace: georef.mode === 'pixel',
    georefReason: georef.reason,
    patchGrid: d.patch_grid
      ? {
          patchSize: d.patch_grid.patch_size,
          stride: d.patch_grid.stride,
          rows: d.patch_grid.rows,
          cols: d.patch_grid.cols,
        }
      : null,
    url: `/api/projects/${d.project_id}/dataset/${d.id}/file`,
    previewUrl: null,
    createdAt: d.created_at,
  };
}

async function projectStats(p: RsalProject): Promise<Project> {
  const base = `/projects/${p.id}`;
  const [metrics, labels, datasets] = await Promise.all([
    rsalGetOptional<RsalMetrics>(`${base}/metrics`),
    rsalGet<RsalLabel[]>(`${base}/labels`),
    rsalGet<RsalDataset[]>(`${base}/dataset`),
  ]);
  const status: Project['status'] =
    p.status === 'completed' ? 'completed' : labels.length > 0 ? 'in_progress' : 'unlabeled';
  return {
    id: String(p.id),
    name: p.name,
    description: p.description,
    status,
    classes: classesFromNames(p.classes),
    studyAreaGeometry: p.study_area_geometry ?? null,
    studyAreaCrs: p.study_area_crs ?? null,
    classificationConfig: {
      internalClasses: ['open_water', 'emergent_vegetation', 'land'],
      binaryOutputInterpretation: p.classification_config?.binary_output_interpretation ?? 'water_vs_non_water',
    },
    createdAt: p.created_at,
    iteration: metrics?.iteration ?? 0,
    accuracy: metrics?.accuracy ?? 0,
    f1: metrics?.f1_macro ?? 0,
    labeledCount: labels.length,
    totalSamples: datasets.reduce((a, d) => a + (d.patch_grid?.total_patches ?? 0), 0),
    modelVersion: metrics ? `${metrics.model_type} · iteration ${metrics.iteration}` : '',
  };
}

function emptyProject(p: RsalProject): Project {
  return {
    id: String(p.id),
    name: p.name,
    description: p.description,
    status: 'unlabeled',
    classes: classesFromNames(p.classes),
    studyAreaGeometry: p.study_area_geometry ?? null,
    studyAreaCrs: p.study_area_crs ?? null,
    classificationConfig: {
      internalClasses: ['open_water', 'emergent_vegetation', 'land'],
      binaryOutputInterpretation: p.classification_config?.binary_output_interpretation ?? 'water_vs_non_water',
    },
    createdAt: p.created_at,
    iteration: 0,
    accuracy: 0,
    f1: 0,
    labeledCount: 0,
    totalSamples: 0,
    modelVersion: '',
  };
}

const PATCH_ID = /^d(\d+)_r(\d+)_c(\d+)$/;

function savedLabelToSample(
  label: RsalLabel,
  projectId: string,
  datasets: RsalDataset[],
): Sample | null {
  const dataset = datasets.find((d) => d.id === label.dataset_id);
  const display = labelToDisplay(dataset, label.geometry, label.coordinate_space);
  if (!display) return null;
  // Every saved label gets the pixel window of its patch, so a reloaded label
  // lines up with the same thumbnail and footprint a fresh query sample has.
  let window: Sample['window'];
  let pixel: Sample['pixel'];
  let pin: { lat: number; lng: number } = { lat: display.lat, lng: display.lng };
  if (dataset) {
    const grid = {
      patchSize: dataset.patch_grid?.patch_size ?? 32,
      stride: dataset.patch_grid?.stride ?? dataset.patch_grid?.patch_size ?? 32,
    };
    const derived = labelPixelWindow(dataset, label.geometry, label.coordinate_space, grid);
    if (derived) {
      window = derived;
      pixel = { x: derived.x0, y: derived.y0 };
      // A fresh query sample is drawn at its patch centre; a saved label must
      // reload exactly there, not at the clicked point (up to half a patch off).
      // Polygons keep their clicked centroid; their ring is drawn anyway.
      if (label.geometry.type === 'Point')
        pin = pixelToDisplay(
          geoContext(dataset),
          (derived.x0 + derived.x1) / 2,
          (derived.y0 + derived.y1) / 2,
        );
    }
  }
  return {
    id: label.sample_id,
    projectId,
    lat: pin.lat,
    lng: pin.lng,
    prediction: label.class_name,
    confidence: 1,
    uncertainty: 0,
    status: 'labeled',
    label: label.class_name,
    note: '',
    iteration: label.iteration,
    batchIndex: 1000,
    geometry: display.geometry.type === 'Polygon' ? display.geometry : null,
    source: 'import', // saved labels stay out of the active review queue
    datasetId: label.dataset_id != null ? String(label.dataset_id) : undefined,
    window,
    pixel,
    bbox: dataset && window ? pixelRectToDisplay(geoContext(dataset), window) : undefined,
    saved: true,
  };
}

/** Convert a browser label draft into an RSAL LabelCreate payload. */
export function toRsalLabel(
  input: LabelInput,
  iteration: number,
  datasets: RsalDataset[],
): Record<string, unknown> {
  const className = input.label;
  if (!className) throw new ApiError('Every submitted label needs a class.');
  const payload: Record<string, unknown> = {
    class_name: className,
    iteration,
  };
  Object.assign(payload, sampleResolutionField(input));

  const patch = PATCH_ID.exec(input.sampleId);
  if (patch) {
    // Review-queue sample: address the exact patch by id + pixel center.
    const dataset = datasets.find((d) => d.id === Number(patch[1]));
    if (!dataset) throw new ApiError(`Dataset ${patch[1]} no longer exists.`, 409);
    if (!input.pixel)
      throw new ApiError('This sample is missing its pixel location; query a fresh batch.');
    payload.sample_id = input.sampleId;
    payload.dataset_id = dataset.id;
    payload.coordinate_space = 'pixel';
    payload.geometry = { type: 'Point', coordinates: [input.pixel.x, input.pixel.y] };
    return payload;
  }

  const dataset = input.datasetId
    ? datasets.find((d) => String(d.id) === input.datasetId)
    : datasets[datasets.length - 1];
  if (!dataset)
    throw new ApiError('Upload a GeoTIFF before adding labels.', 409);
  payload.dataset_id = dataset.id;
  // Saved samples (import-, pt_, poly_) keep their id so re-submission stores a
  // corrected version; fresh manual drafts let RSAL derive the canonical id.
  if (!input.sampleId.startsWith('manual-')) payload.sample_id = input.sampleId;

  const geometry = input.geometry ??
    (input.lat !== undefined && input.lng !== undefined
      ? { type: 'Point' as const, coordinates: [input.lng, input.lat] }
      : null);
  if (!geometry) throw new ApiError('Every label needs a location.');

  // Display -> pixel goes through the shared transform, so submission cannot
  // disagree with where the marker and the thumbnail were drawn.
  const ctx = geoContext(dataset);
  const georeferenced = isGeoreferenced(dataset);
  const convertPair = (lng: number, lat: number): [number, number] => {
    const pixel = displayToPixel(ctx, lng, lat);
    if (!Number.isFinite(pixel.x) || !Number.isFinite(pixel.y))
      throw new ApiError('Could not reproject this label into the dataset CRS.', 422);
    if (!georeferenced) return [pixel.x, pixel.y];
    const [x, y] = applyAffine(dataset.transform!, pixel.x, pixel.y);
    return [x, y];
  };
  payload.coordinate_space = georeferenced ? 'map' : 'pixel';
  if (geometry.type === 'Point') {
    const [lng, lat] = geometry.coordinates as number[];
    payload.geometry = { type: 'Point', coordinates: convertPair(lng, lat) };
  } else {
    const rings = geometry.coordinates as number[][][];
    payload.geometry = {
      type: 'Polygon',
      coordinates: rings.map((ring) => ring.map(([lng, lat]) => convertPair(lng, lat))),
    };
  }
  return payload;
}

const STRATEGIES: Record<string, { strategy: string; method?: string }> = {
  entropy: { strategy: 'uncertainty', method: 'entropy' },
  margin: { strategy: 'uncertainty', method: 'margin' },
  'least-confidence': { strategy: 'uncertainty', method: 'least_confidence' },
  diversity: { strategy: 'diversity' },
  hybrid: { strategy: 'hybrid', method: 'entropy' },
  som: { strategy: 'som', method: 'entropy' },
};

function toSomData(s: RsalSomResponse): SomData {
  return {
    projectId: String(s.project_id),
    datasetId: String(s.dataset_id),
    rows: s.rows,
    cols: s.cols,
    epochs: s.epochs,
    totalPatches: s.total_patches,
    labeledPatches: s.labeled_patches,
    activeNeurons: s.active_neurons,
    quantizationError: s.quantization_error,
    topographicError: s.topographic_error,
    modelIteration: s.model_iteration,
    bands: s.bands,
    classes: s.classes,
    uMatrix: s.u_matrix,
    hitGrid: s.hit_grid,
    cells: s.cells.map((c) => ({
      row: c.row,
      col: c.col,
      hitCount: c.hit_count,
      labeledCount: c.labeled_count,
      unlabeledCount: c.unlabeled_count,
      uValue: c.u_value,
      quantizationError: c.quantization_error,
      dominantLabel: c.dominant_label,
      labelCounts: c.label_counts,
      predictedClass: c.predicted_class,
      predictionCounts: c.prediction_counts,
      meanConfidence: c.mean_confidence,
      meanUncertainty: c.mean_uncertainty,
      bandMeans: c.band_means,
      bandProfile: c.band_profile,
      representativeSampleId: c.representative_sample_id,
      sampleIds: c.sample_ids,
    })),
  };
}

// ------------------------------------------------------------------ helpers
async function getDatasets(projectId: string): Promise<RsalDataset[]> {
  return rsalGet<RsalDataset[]>(`/projects/${pid(projectId)}/dataset`);
}

function json(data: unknown, status = 200) {
  return NextResponse.json(data, { status });
}

async function handle(fn: () => Promise<NextResponse>): Promise<NextResponse> {
  try {
    return await fn();
  } catch (error) {
    if (error instanceof ApiError) return json({ error: error.message }, error.status);
    if (error instanceof SyntaxError)
      return json({ error: 'The request body is not valid JSON.' }, 400);
    console.error('[TerraLab API]', error);
    return json({ error: 'We could not complete this request. Please try again.' }, 500);
  }
}

// ------------------------------------------------------------------ routes
export async function healthHandler(): Promise<NextResponse> {
  return handle(async () => {
    try {
      const data = await rsalGet<{ status: string; version: string }>('/health');
      return json({ ok: data.status === 'ok', backend: data.version });
    } catch (error) {
      return json(
        { ok: false, error: error instanceof Error ? error.message : 'Backend unavailable.' },
        502,
      );
    }
  });
}

export async function projectsHandler(request: NextRequest): Promise<NextResponse> {
  return handle(async () => {
    if (request.method === 'GET') {
      const projects = await rsalGet<RsalProject[]>('/projects');
      return json(await Promise.all(projects.map(projectStats)));
    }
    const body = await request.json();
    const names: string[] = Array.isArray(body.classes)
      ? body.classes.map((c: { name?: string } | string) =>
          typeof c === 'string' ? c : (c.name ?? ''),
        )
      : [];
    // `generic_classes` must be forwarded: without it the engine only accepts the
    // WBALC water taxonomy (open_water, emergent_vegetation, land) and answers 422
    // for any other class list, which is how a caller with its own classes used to
    // fail at project creation.
    const created = await rsalPost<RsalProject>('/projects', {
      name: body.name,
      description: body.description ?? '',
      classes: names,
      generic_classes: body.genericClasses ?? false,
      study_area_geometry: body.studyAreaGeometry ?? null,
      study_area_crs: body.studyAreaCrs ?? null,
      classification_config: body.classificationConfig
        ? {
            internal_classes: body.classificationConfig.internalClasses,
            binary_output_interpretation: body.classificationConfig.binaryOutputInterpretation,
          }
        : undefined,
    });
    return json(emptyProject(created), 201);
  });
}

export async function projectHandler(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  return handle(async () => {
    const { id = '' } = await context.params;
    if (request.method === 'DELETE') {
      const response = await rsalFetch(`/projects/${pid(id)}`, { method: 'DELETE' });
      if (!response.ok && response.status !== 204)
        throw new ApiError('The project could not be deleted.', response.status);
      return json({ deleted: true });
    }
    const project = await rsalGet<RsalProject>(`/projects/${pid(id)}`);
    return json(await projectStats(project));
  });
}

export async function datasetListHandler(
  _request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  return handle(async () => {
    const { id = '' } = await context.params;
    return json((await getDatasets(id)).map(toDataset));
  });
}

export async function datasetItemHandler(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  return handle(async () => {
    const { id = '', itemId = '' } = await context.params;
    const path = `/projects/${pid(id)}/dataset/${encodeURIComponent(itemId)}`;
    if (request.method === 'DELETE') {
      const response = await rsalFetch(path, { method: 'DELETE' });
      if (!response.ok && response.status !== 204) {
        const data = await response.json().catch(() => null);
        throw new ApiError(data?.detail ?? 'The dataset could not be deleted.', response.status);
      }
      return json({ deleted: true });
    }
    return json(toDataset(await rsalGet<RsalDataset>(path)));
  });
}

export async function datasetFileHandler(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  return handle(async () => {
    const { id = '', itemId = '' } = await context.params;
    // Forward byte ranges so the browser can read a 32 px patch out of a large
    // GeoTIFF instead of downloading the whole scene for one thumbnail.
    const range = request.headers.get('range');
    const response = await rsalFetch(
      `/projects/${pid(id)}/dataset/${encodeURIComponent(itemId)}/file`,
      range ? { headers: { range } } : undefined,
    );
    if (!response.ok && response.status !== 206) {
      const data = await response.json().catch(() => null);
      throw new ApiError(data?.detail ?? 'The raster file could not be loaded.', response.status);
    }
    const headers: Record<string, string> = {
      'content-type': response.headers.get('content-type') ?? 'image/tiff',
      'cache-control': 'private, max-age=3600',
      'x-content-type-options': 'nosniff',
      'accept-ranges': 'bytes',
    };
    const contentRange = response.headers.get('content-range');
    if (contentRange) headers['content-range'] = contentRange;
    return new NextResponse(response.body, { status: response.status, headers });
  });
}

export async function actionHandler(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  return handle(async () => {
    const { id = '', action = '' } = await context.params;
    const base = `/projects/${pid(id)}`;
    const method = request.method;

    if (action === 'metrics' && method === 'GET') {
      const [project, latest, history, labels, datasets] = await Promise.all([
        rsalGet<RsalProject>(base),
        rsalGetOptional<RsalMetrics>(`${base}/metrics`),
        rsalGet<RsalMetrics[]>(`${base}/metrics/history`),
        rsalGet<RsalLabel[]>(`${base}/labels`),
        getDatasets(id),
      ]);
      const classes = classesFromNames(project.classes);
      const counts = new Map<string, number>(project.classes.map((c) => [c, 0]));
      for (const label of labels)
        counts.set(label.class_name, (counts.get(label.class_name) ?? 0) + 1);
      const metrics: Metrics = {
        accuracy: latest?.accuracy ?? 0,
        f1: latest?.f1_macro ?? 0,
        labeledCount: labels.length,
        totalSamples: datasets.reduce((a, d) => a + (d.patch_grid?.total_patches ?? 0), 0),
        iteration: latest?.iteration ?? 0,
        curve: history.map((m, i) => toIteration(m, history[i - 1]?.n_samples ?? 0)),
        distribution: classes.map((c) => ({
          name: c.name,
          color: c.color,
          value: counts.get(c.id) ?? 0,
        })),
        confusionMatrix: latest?.confusion_matrix ?? [],
        perClass: classes.map((c) => ({
          name: c.name,
          color: c.color,
          precision: latest?.per_class?.[c.id]?.precision ?? 0,
          recall: latest?.per_class?.[c.id]?.recall ?? 0,
          f1: latest?.per_class?.[c.id]?.f1 ?? 0,
          support: latest?.per_class?.[c.id]?.support ?? 0,
        })),
        evaluation: latest?.evaluation ?? '',
      };
      return json(metrics);
    }

    if (action === 'labels' && method === 'GET') {
      const [labels, datasets] = await Promise.all([
        rsalGet<RsalLabel[]>(`${base}/labels`),
        getDatasets(id),
      ]);
      const samples = labels
        .map((l) => savedLabelToSample(l, id, datasets))
        .filter((s): s is Sample => s !== null);
      return json(samples);
    }

    if (action === 'exports' && method === 'GET') {
      return json(await rsalGet<unknown[]>(`${base}/exports`));
    }

    if (action === 'history' && method === 'GET')
      return json(await rsalGet<RsalLabel[]>(`${base}/history`));

    if (action === 'som' && (method === 'GET' || method === 'POST')) {
      if (method === 'POST') {
        const body = await request.json().catch(() => ({}));
        const result = await rsalPost<RsalSomResponse>(`${base}/som`, {
          ...(body.datasetId && /^\d+$/.test(String(body.datasetId))
            ? { dataset_id: Number(body.datasetId) }
            : {}),
          ...(body.rows ? { rows: Number(body.rows) } : {}),
          ...(body.cols ? { cols: Number(body.cols) } : {}),
          ...(body.epochs ? { epochs: Number(body.epochs) } : {}),
        });
        return json(toSomData(result));
      }
      const url = new URL(request.url);
      const qs = new URLSearchParams();
      const did = url.searchParams.get('datasetId');
      const rows = url.searchParams.get('rows');
      const cols = url.searchParams.get('cols');
      const epochs = url.searchParams.get('epochs');
      if (did && /^\d+$/.test(did)) qs.set('dataset_id', did);
      if (rows && /^\d+$/.test(rows)) qs.set('rows', rows);
      if (cols && /^\d+$/.test(cols)) qs.set('cols', cols);
      if (epochs && /^\d+$/.test(epochs)) qs.set('epochs', epochs);
      const suffix = qs.toString() ? `?${qs.toString()}` : '';
      const result = await rsalGet<RsalSomResponse>(`${base}/som${suffix}`);
      return json(toSomData(result));
    }

    if (action === 'som-classify' && method === 'POST') {
      const body = await request.json().catch(() => ({}));
      const rows = Math.min(Math.max(Number(body.rows) || 4, 2), 32);
      const cols = Math.min(Math.max(Number(body.cols) || 4, 2), 32);
      const nClusters =
        body.nClusters != null && Number(body.nClusters) >= 2
          ? Number(body.nClusters)
          : null;
      const result = await rsalPost<RsalSomClassifyResponse>(`${base}/som/classify`, {
        rows,
        cols,
        ...(nClusters ? { n_clusters: nClusters } : {}),
        epochs: Math.min(Math.max(Number(body.epochs) || 50, 5), 500),
        resolution: body.resolution === 'patch' ? 'patch' : 'pixel',
        include_map: false,
        ...(body.datasetId && /^\d+$/.test(String(body.datasetId))
          ? { dataset_id: Number(body.datasetId) }
          : {}),
      });
      const mapped: SomClassification = {
        projectId: String(result.project_id),
        datasetId: String(result.dataset_id),
        exportId: result.export_id,
        rows: result.rows,
        cols: result.cols,
        epochs: result.epochs,
        nClusters: result.n_clusters,
        resolution: result.resolution,
        shape: result.shape,
        totalValid: result.total_valid,
        nodataCount: result.nodata_count,
        quantizationError: result.quantization_error,
        topographicError: result.topographic_error,
        uMatrix: result.u_matrix,
        neuronClusters: result.neuron_clusters,
        neuronHits: result.neuron_hits,
        clusters: result.clusters.map((c) => ({
          clusterId: c.cluster_id,
          label: c.label,
          color: c.color,
          pixelCount: c.pixel_count,
          fraction: c.fraction,
          bandMeans: c.band_means,
          bandProfile: c.band_profile,
          neurons: c.neurons,
        })),
        downloadUrl: `/api/projects/${result.project_id}/som-download?exportId=${result.export_id}&datasetId=${result.dataset_id}`,
      };
      return json(mapped);
    }

    if (action === 'som-download' && method === 'GET') {
      const url = new URL(request.url);
      const qs = new URLSearchParams();
      const did = url.searchParams.get('datasetId');
      const eid = url.searchParams.get('exportId');
      if (did && /^\d+$/.test(did)) qs.set('dataset_id', did);
      if (eid && /^\d+$/.test(eid)) qs.set('export_id', eid);
      const suffix = qs.toString() ? `?${qs.toString()}` : '';
      const response = await rsalFetch(`${base}/som/download${suffix}`);
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new ApiError(
          data?.detail ?? 'The SOM classification GeoTIFF could not be exported.',
          response.status,
        );
      }
      return new NextResponse(response.body, {
        headers: {
          'content-type': response.headers.get('content-type') ?? 'image/tiff',
          'content-disposition': `attachment; filename="project_${id}_unsupervised_som.tif"`,
          'cache-control': 'private, max-age=3600',
          'x-content-type-options': 'nosniff',
        },
      });
    }

    if (action === 'query' && method === 'POST') {
      const body = await request.json();
      const mapped = STRATEGIES[body.strategy ?? 'entropy'];
      if (!mapped) throw new ApiError(`Unknown sampling strategy '${body.strategy}'.`);
      const somCell =
        Array.isArray(body.somCell) && body.somCell.length === 2
          ? [Number(body.somCell[0]), Number(body.somCell[1])]
          : undefined;
      const [result, datasets] = await Promise.all([
        rsalPost<RsalQueryResponse>(`${base}/query`, {
          strategy: mapped.strategy,
          ...(mapped.method ? { method: mapped.method } : {}),
          batch_size: Math.min(Math.max(Number(body.batchSize) || 12, 1), 10000),
          ...(body.datasetId && /^\d+$/.test(String(body.datasetId))
            ? { dataset_id: Number(body.datasetId) }
            : {}),
          ...(body.somRows ? { som_rows: Number(body.somRows) } : {}),
          ...(body.somCols ? { som_cols: Number(body.somCols) } : {}),
          ...(body.somEpochs ? { som_epochs: Number(body.somEpochs) } : {}),
          ...(somCell ? { som_cell: somCell } : {}),
        }),
        getDatasets(id),
      ]);
      const samples: Sample[] = result.samples.map((s, index) => {
        const dataset = datasets.find((d) => d.id === s.dataset_id);
        const display = dataset
          ? pixelToDisplay(geoContext(dataset), s.coords.center_x, s.coords.center_y)
          : { lng: s.coords.center_x, lat: s.coords.center_y };
        const window = dataset
          ? { x0: s.coords.x0, y0: s.coords.y0, x1: s.coords.x1, y1: s.coords.y1 }
          : undefined;
        const bbox: Bounds | undefined =
          dataset && window ? pixelRectToDisplay(geoContext(dataset), window) : undefined;
        return {
          id: s.sample_id,
          projectId: id,
          lat: display.lat,
          lng: display.lng,
          prediction: s.prediction ?? '',
          confidence: s.confidence ?? 0,
          uncertainty: s.uncertainty ?? 0,
          status: 'pending',
          label: null,
          note: '',
          iteration: result.model_iteration ?? 0,
          batchIndex: index,
          geometry: null,
          source: 'query',
          datasetId: String(s.dataset_id),
          // Labels are attached to the patch origin, which is what the backend's
          // `d{dataset}_r{row}_c{col}` id means; the centre is display only.
          pixel: window ? { x: window.x0, y: window.y0 } : undefined,
          window,
          bbox,
        };
      });
      return json({ samples, existing: false });
    }

    if (action === 'labels' && method === 'POST') {
      const body = await request.json();
      const inputs: LabelInput[] = Array.isArray(body.labels) ? body.labels : [];
      const trainable = inputs.filter((l) => l.status === 'labeled' && l.label);
      if (!trainable.length) return json({ saved: 0 });
      const [metrics, datasets] = await Promise.all([
        rsalGetOptional<RsalMetrics>(`${base}/metrics`),
        getDatasets(id),
      ]);
      const labels = trainable.map((l) => toRsalLabel(l, metrics?.iteration ?? 0, datasets));
      await rsalPost(`${base}/labels`, { labels });
      return json({ saved: labels.length }, 201);
    }

    if (action === 'train' && method === 'POST') {
      const body = await request.json().catch(() => ({}));
      // Forward every option the workspace exposes. Dropping them silently made
      // "train at pixel resolution" impossible from the UI and hid the
      // evaluation strategy behind API-only calls.
      const result = await rsalPost<RsalTrainResponse>(`${base}/train`, trainBody(body));
      const history = await rsalGetOptional<RsalMetrics[]>(`${base}/metrics/history`);
      const previous = history?.filter((m) => m.id !== result.metrics.id).pop();
      return json({ iteration: toIteration(result.metrics, previous?.n_samples ?? 0) }, 201);
    }

    if (action === 'upload' && method === 'POST') {
      const form = await request.formData();
      const file = form.get('file');
      if (!(file instanceof File) || !/\.tiff?$/i.test(file.name))
        throw new ApiError('Choose a .tif or .tiff GeoTIFF file.');
      if (file.size === 0 || file.size > 100 * 1024 * 1024)
        throw new ApiError('GeoTIFFs must be non-empty and smaller than 100 MB.');
      const upstream = new FormData();
      upstream.append('file', file, file.name);
      const response = await rsalFetch(`${base}/upload`, { method: 'POST', body: upstream });
      const data = await response.json().catch(() => null);
      if (!response.ok)
        throw new ApiError(
          typeof data?.detail === 'string' ? data.detail : 'The upload could not be processed.',
          response.status,
        );
      return json(toDataset(data as RsalDataset), 201);
    }

    throw new ApiError('Endpoint not found.', 404);
  });
}

export async function itemHandler(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  return handle(async () => {
    const { id = '', action = '', itemId = '' } = await context.params;
    const base = `/projects/${pid(id)}`;
    if (action === 'labels' && request.method === 'DELETE') {
      const response = await rsalFetch(`${base}/labels/${encodeURIComponent(itemId)}`, {
        method: 'DELETE',
      });
      if (!response.ok && response.status !== 204) {
        const data = await response.json().catch(() => null);
        throw new ApiError(
          typeof data?.detail === 'string' ? data.detail : 'The label could not be deleted.',
          response.status,
        );
      }
      return json({ deleted: true });
    }
    if (action === 'dataset' && request.method === 'DELETE') {
      const response = await rsalFetch(`${base}/dataset/${encodeURIComponent(itemId)}`, {
        method: 'DELETE',
      });
      if (!response.ok && response.status !== 204)
        throw new ApiError('The dataset could not be deleted.', response.status);
      return json({ deleted: true });
    }
    throw new ApiError('Endpoint not found.', 404);
  });
}
