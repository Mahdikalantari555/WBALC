/**
 * Map-layer + export routes for the TerraLab workspace, backed by RSAL.
 *
 * Layers:   GET /api/projects/{id}/map?layer=hard|uncertainty&method&datasetId&iteration
 * Files:    GET /api/projects/{id}/map/export?format=tif|png|csv&layer=...&method&datasetId
 *
 * Every request is made server-side (RSAL_API_URL never reaches the browser).
 */
import { NextRequest, NextResponse } from 'next/server';
import { isUncertaintyMethod, UNCERTAINTY_METHODS, type UncertaintyMethod } from '@/lib/layers';
import { ApiError, rsalFetch, rsalGet, type RsalDataset } from './rsal';

export interface MapField {
  layer: 'hard' | 'uncertainty';
  method: string | null;
  projectId: string;
  datasetId: string;
  modelIteration: number;
  trainingRunId: number;
  classes: string[];
  /** "pixel" = one prediction per source pixel, "patch" = one per patch cell. */
  resolution: string;
  grid: { rows: number; cols: number; patchSize: number; stride: number };
  /** rows × cols; `null` where the patch has no valid pixels. */
  values: (number | null)[][];
  valid: boolean[][];
  min: number;
  max: number;
  stale: boolean;
}

interface RsalMapField {
  layer: 'hard' | 'uncertainty';
  method: string | null;
  project_id: number;
  dataset_id: number;
  model_iteration: number;
  training_run_id: number;
  classes: string[];
  resolution?: string;
  grid: {
    rows: number;
    cols: number;
    patch_size: number;
    stride: number;
    region: { x0: number; y0: number; x1: number; y1: number };
  };
  values: (number | null)[][];
  valid: boolean[][];
  min: number;
  max: number;
  stale: boolean;
}

export function methodOr400(method: string | null | undefined): UncertaintyMethod {
  const value = method ?? 'entropy';
  if (!isUncertaintyMethod(value))
    throw new ApiError(
      `Unknown uncertainty method '${method}'; use ${UNCERTAINTY_METHODS.join(', ')}.`,
      422,
    );
  return value;
}

function pid(id: string): string {
  if (!/^\d+$/.test(id)) throw new ApiError('Project not found.', 404);
  return id;
}

function fail(error: unknown): NextResponse {
  if (error instanceof ApiError) return NextResponse.json({ error: error.message }, { status: error.status });
  console.error('[TerraLab map route]', error);
  return NextResponse.json({ error: 'We could not complete this request. Please try again.' }, { status: 500 });
}

/** Class colours come from the backend palette so the map and exports agree. */
export async function classColors(projectId: string): Promise<string[]> {
  const data = await rsalGet<{ classes: { color: string }[] }>(
    `/projects/${pid(projectId)}/legends/classes`,
  );
  return data.classes.map((c) => c.color);
}

export async function mapFieldHandler(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  try {
    const { id } = await context.params;
    const params = new URL(request.url).searchParams;
    const layer = params.get('layer') === 'uncertainty' ? 'uncertainty' : 'hard';
    const method = layer === 'uncertainty' ? methodOr400(params.get('method')) : undefined;
    const datasetId = params.get('datasetId');
    const iteration = params.get('iteration');

    const query = new URLSearchParams({ layer });
    if (method) query.set('method', method);
    if (datasetId && /^\d+$/.test(datasetId)) query.set('dataset_id', datasetId);
    if (iteration && /^\d+$/.test(iteration)) query.set('iteration', iteration);

    const [field, colors] = await Promise.all([
      rsalGet<RsalMapField>(`/projects/${pid(id)}/predict/map?${query.toString()}`),
      classColors(id).catch(() => []),
    ]);

    const payload: MapField & { colors: string[] } = {
      layer: field.layer,
      method: field.method,
      projectId: String(field.project_id),
      datasetId: String(field.dataset_id),
      modelIteration: field.model_iteration,
      trainingRunId: field.training_run_id,
      classes: field.classes,
      resolution: field.resolution === 'pixel' ? 'pixel' : 'patch',
      grid: {
        rows: field.grid.rows,
        cols: field.grid.cols,
        patchSize: field.grid.patch_size,
        stride: field.grid.stride,
      },
      values: field.values,
      valid: field.valid,
      min: field.min,
      max: field.max,
      stale: field.stale,
      colors,
    };
    return NextResponse.json(payload, { headers: { 'cache-control': 'no-store' } });
  } catch (error) {
    return fail(error);
  }
}

const RSAL_TYPE: Record<string, string> = {
  hard: 'hard',
  uncertainty: 'uncertainty',
  probability: 'probability',
};

/** Probability maps only exist as a multi-band GeoTIFF (no palette, no table). */
function layerOr400(value: string | null): 'hard' | 'uncertainty' | 'probability' {
  const layer = value === 'uncertainty' || value === 'probability' ? value : 'hard';
  return layer;
}

export async function mapExportHandler(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  try {
    const { id } = await context.params;
    const params = new URL(request.url).searchParams;
    const layer = layerOr400(params.get('layer'));
    const format = (params.get('format') ?? 'tif').toLowerCase();
    const method = layer === 'uncertainty' ? methodOr400(params.get('method')) : undefined;

    const datasetId = params.get('datasetId');
    const suffix = method ? `method=${method}` : '';

    const upstream = (path: string) =>
      rsalFetch(path).then(async (response) => {
        if (!response.ok) {
          const data = await response.json().catch(() => null);
          throw new ApiError(
            typeof data?.detail === 'string' ? data.detail : 'The export could not be generated.',
            response.status,
          );
        }
        return response;
      });

    if (format === 'tif' || format === 'tiff' || format === 'geotiff') {
      const query = new URLSearchParams();
      if (datasetId && /^\d+$/.test(datasetId)) query.set('dataset_id', datasetId);
      if (suffix) query.set('method', method!);
      const response = await upstream(
        `/projects/${pid(id)}/download/${RSAL_TYPE[layer]}?${query.toString()}`,
      );
      return new NextResponse(response.body, {
        headers: {
          'content-type': 'image/tiff',
          'content-disposition':
            response.headers.get('content-disposition') ??
            `attachment; filename="${layer}${method ? `_${method}` : ''}.tif"`,
        },
      });
    }

    if ((format === 'png' || format === 'csv') && layer === 'probability')
      throw new ApiError('Probability maps are only available as GeoTIFF (tif).', 422);

    if (format === 'png' || format === 'csv') {
      const query = new URLSearchParams({ scale: params.get('scale') ?? '8' });
      if (datasetId && /^\d+$/.test(datasetId)) query.set('dataset_id', datasetId);
      if (suffix) query.set('method', method!);
      const response = await upstream(
        `/projects/${pid(id)}/exports/${RSAL_TYPE[layer]}.${format}?${query.toString()}`,
      );
      return new NextResponse(response.body, {
        headers: {
          'content-type': format === 'png' ? 'image/png' : 'text/csv',
          'content-disposition':
            response.headers.get('content-disposition') ??
            `attachment; filename="${layer}${method ? `_${method}` : ''}.${format}"`,
        },
      });
    }

    throw new ApiError(`Unsupported export format '${format}'; use tif, png or csv.`, 422);
  } catch (error) {
    return fail(error);
  }
}

/** Datasets whose band count the trained model can actually classify. */
export function modelCompatible(
  dataset: RsalDataset,
  bands: number | null | undefined,
): boolean {
  return bands == null || dataset.bands === bands;
}
