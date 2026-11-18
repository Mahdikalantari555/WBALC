/**
 * Thin HTTP client for the RSAL FastAPI backend.
 * Server-side only: RSAL_API_URL / RSAL_API_TOKEN never reach the browser.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 400,
  ) {
    super(message);
  }
}

const baseUrl = () => (process.env.RSAL_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export function rsalUrl(path: string): string {
  return `${baseUrl()}${path}`;
}

export function rsalHeaders(): Headers {
  const headers = new Headers();
  if (process.env.RSAL_API_TOKEN)
    headers.set('authorization', `Bearer ${process.env.RSAL_API_TOKEN}`);
  return headers;
}

/** Fetch the backend, converting network failures into actionable 502s. */
export async function rsalFetch(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(rsalUrl(path), {
      ...init,
      headers: (() => {
        const h = rsalHeaders();
        new Headers(init?.headers).forEach((v, k) => h.set(k, v));
        return h;
      })(),
      cache: 'no-store',
      signal: init?.signal ?? AbortSignal.timeout(180_000),
    });
  } catch {
    throw new ApiError(
      'The WBALC backend is unreachable. Start it with `uvicorn app.main:app --host 0.0.0.0 --port 8000` (or docker compose up) and check RSAL_API_URL.',
      502,
    );
  }
  return response;
}

function detailMessage(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail))
      return detail
        .map((d) =>
          d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d),
        )
        .join('; ');
  }
  return `The backend returned an error (${status}).`;
}

/** JSON request; RSAL error `detail` strings pass through with their status. */
export async function rsalJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await rsalFetch(path, init);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(detailMessage(data, response.status), response.status);
  return data as T;
}

export async function rsalGet<T>(path: string): Promise<T> {
  return rsalJson<T>(path);
}

export async function rsalPost<T>(path: string, body: unknown): Promise<T> {
  return rsalJson<T>(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** Like rsalGet but returns null on 404 (e.g. metrics before the first run). */
export async function rsalGetOptional<T>(path: string): Promise<T | null> {
  try {
    return await rsalGet<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

// ------------------------------------------------------------ RSAL shapes
export interface RsalProject {
  id: number;
  name: string;
  description: string;
  classes: string[];
  status: string;
  study_area_geometry?: Record<string, unknown> | null;
  study_area_crs?: string | null;
  classification_config?: {
    internal_classes: string[];
    binary_output_interpretation: 'water_vs_non_water' | 'open_water_vs_other';
  };
  created_at: string;
  updated_at: string;
}
export interface RsalDataset {
  id: number;
  project_id: number;
  filename: string;
  crs: string | null;
  transform: number[] | null;
  width: number;
  height: number;
  bands: number;
  dtype: string;
  nodata: number | null;
  bounds: [number, number, number, number] | null;
  created_at: string;
  size_bytes: number;
  patch_grid: {
    patch_size: number;
    stride: number;
    rows: number;
    cols: number;
    total_patches: number;
  } | null;
}
export interface RsalLabel {
  id: number;
  project_id: number;
  dataset_id: number | null;
  sample_id: string;
  sample_type: string;
  geometry: { type: 'Point' | 'Polygon'; coordinates: unknown };
  coordinate_space: 'pixel' | 'map';
  class_name: string;
  iteration: number;
  version: number;
  created_at: string;
}
export interface RsalMetrics {
  id: number;
  project_id: number;
  iteration: number;
  model_type: string;
  n_samples: number;
  accuracy: number;
  f1_macro: number;
  f1_weighted: number;
  confusion_matrix: number[][];
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  classes: string[];
  evaluation: string;
  created_at: string;
}
export interface RsalQuerySample {
  sample_id: string;
  dataset_id: number;
  coords: {
    row: number;
    col: number;
    x0: number;
    y0: number;
    x1: number;
    y1: number;
    center_x: number;
    center_y: number;
  };
  geo_coords: { bbox?: number[]; center?: number[] } | null;
  prediction: string | null;
  confidence: number | null;
  uncertainty: number | null;
}
export interface RsalQueryResponse {
  strategy: string;
  method: string | null;
  batch_size: number;
  model_iteration: number | null;
  samples: RsalQuerySample[];
}
export interface RsalTrainResponse {
  id: number;
  project_id: number;
  iteration: number;
  model_type: string;
  /** "pixel" | "patch": which feature family produced this checkpoint. */
  resolution?: string;
  checkpoint: string;
  n_samples: number;
  metrics: RsalMetrics;
}
export interface RsalSomCell {
  row: number;
  col: number;
  hit_count: number;
  labeled_count: number;
  unlabeled_count: number;
  u_value: number;
  quantization_error: number;
  dominant_label: string | null;
  label_counts: Record<string, number>;
  predicted_class: string | null;
  prediction_counts: Record<string, number>;
  mean_confidence: number | null;
  mean_uncertainty: number | null;
  band_means: number[];
  band_profile: number[];
  representative_sample_id: string | null;
  sample_ids: string[];
}
export interface RsalSomResponse {
  project_id: number;
  dataset_id: number;
  rows: number;
  cols: number;
  epochs: number;
  total_patches: number;
  labeled_patches: number;
  active_neurons: number;
  quantization_error: number;
  topographic_error: number;
  model_iteration: number | null;
  bands: number;
  classes: string[];
  u_matrix: number[][];
  hit_grid: number[][];
  cells: RsalSomCell[];
}
export interface RsalSomClusterSummary {
  cluster_id: number;
  label: string;
  color: [number, number, number];
  pixel_count: number;
  fraction: number;
  band_means: number[];
  band_profile: number[];
  neurons: [number, number][];
}
export interface RsalSomClassifyResponse {
  project_id: number;
  dataset_id: number;
  export_id: number;
  rows: number;
  cols: number;
  epochs: number;
  n_clusters: number;
  resolution: 'pixel' | 'patch';
  shape: [number, number];
  total_valid: number;
  nodata_count: number;
  quantization_error: number;
  topographic_error: number;
  u_matrix: number[][];
  neuron_clusters: number[][];
  neuron_hits: number[][];
  clusters: RsalSomClusterSummary[];
  exports: Record<string, string>;
}
