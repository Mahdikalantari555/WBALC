/**
 * Thin HTTP client for the WBALC (RSAL) FastAPI engine.
 *
 * Server-side only: `RSAL_API_URL` and `RSAL_API_TOKEN` are read through
 * `$env/dynamic/private` so they never reach the browser. Every route handler in
 * `src/routes/api/**` goes through this module; the browser never talks to the
 * engine directly (no CORS surface, no secret URL in the client bundle).
 */
import { env } from '$env/dynamic/private';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export const UNAVAILABLE_MESSAGE =
  'The WBALC backend is unreachable. Start it with `uvicorn app.main:app --host 0.0.0.0 --port 8000` (or `docker compose up`), then check RSAL_API_URL.';

function baseUrl(): string {
  return (env.RSAL_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
}

export function rsalUrl(path: string): string {
  return `${baseUrl()}${path.startsWith('/') ? path : `/${path}`}`;
}

function headers(extra?: HeadersInit): Headers {
  const result = new Headers(extra);
  if (env.RSAL_API_TOKEN) result.set('authorization', `Bearer ${env.RSAL_API_TOKEN}`);
  return result;
}

function detailMessage(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item
            ? String((item as { msg: unknown }).msg)
            : String(item),
        )
        .join('; ');
    }
  }
  return `The backend returned an error (${status}).`;
}

/** Fetch the engine, converting connection failures into actionable 502s. */
export async function rsalFetch(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(rsalUrl(path), {
      ...init,
      headers: headers(init?.headers),
      cache: 'no-store',
      signal: init?.signal ?? AbortSignal.timeout(180_000),
    });
  } catch {
    throw new ApiError(UNAVAILABLE_MESSAGE, 502);
  }
  return response;
}

export async function rsalJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await rsalFetch(path, init);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(detailMessage(data, response.status), response.status);
  return data as T;
}

export const rsalGet = <T>(path: string) => rsalJson<T>(path);

export const rsalPost = <T>(path: string, body: unknown) =>
  rsalJson<T>(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });

/** `null` on 404 (e.g. metrics before the first run) instead of throwing. */
export async function rsalGetOptional<T>(path: string): Promise<T | null> {
  try {
    return await rsalGet<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function rsalDelete(path: string): Promise<void> {
  const response = await rsalFetch(path, { method: 'DELETE' });
  if (!response.ok && response.status !== 204) {
    const data = await response.json().catch(() => null);
    throw new ApiError(detailMessage(data, response.status), response.status);
  }
}

/** Multipart upload (dataset or scene registration). */
export async function rsalUpload<T>(path: string, form: FormData): Promise<T> {
  return rsalJson<T>(path, { method: 'POST', body: form });
}

/** Cheap liveness probe used by `/api/health`. */
export async function rsalHealth(): Promise<{ ok: boolean; detail: string }> {
  try {
    const response = await rsalFetch('/health');
    if (response.ok) return { ok: true, detail: 'ok' };
    return { ok: false, detail: `HTTP ${response.status}` };
  } catch (error) {
    return { ok: false, detail: error instanceof ApiError ? error.message : String(error) };
  }
}

// ------------------------------------------------------------- RSAL shapes
export interface RsalProject {
  id: number;
  name: string;
  description: string;
  classes: string[];
  status: string;
  study_area_geometry: Record<string, unknown> | null;
  study_area_crs: string | null;
  classification_config: {
    internal_classes: string[];
    binary_output_interpretation: 'water_vs_non_water' | 'open_water_vs_other';
    label_aliases?: Record<string, string[]>;
  };
  /** Versioned water taxonomy snapshot; null for a generic/legacy project. */
  taxonomy?: RsalTaxonomy | null;
  created_at: string;
  updated_at: string;
}

export interface RsalBinarySummary {
  interpretation: 'water_vs_non_water' | 'open_water_vs_other';
  version: string;
  available: boolean;
  mapping: Record<string, string>;
  source_classes: string[];
  missing_classes: string[];
  reason: string | null;
  taxonomy_version: string | null;
  exports: Record<string, string>;
}

export interface RsalTaxonomy {
  version: string;
  classes: string[];
  display_names: Record<string, string>;
  aliases: Record<string, string[]>;
  crosswalk: Record<string, string>;
  binary_interpretation: 'water_vs_non_water' | 'open_water_vs_other';
  source: string;
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
  /** Content hash recorded while the bytes were written; null = legacy upload. */
  content_sha256?: string | null;
  /**
   * Ordered band identity the file declares (`declared: false` when it names no
   * bands). Optional: an older engine omits it, and "unknown" must not be
   * silently read as "declared".
   */
  band_schema?: RsalBandSchema | null;
  patch_grid: {
    patch_size: number;
    stride: number;
    rows: number;
    cols: number;
    total_patches: number;
  } | null;
}

export interface RsalBandSchema {
  version: string;
  band_count: number;
  band_names: string[] | null;
  sensor: string | null;
  declared: boolean;
  source: string;
  digest: string | null;
}

export interface RsalScene {
  id: number;
  project_id: number;
  acquisition_datetime: string | null;
  platform: string | null;
  sensor: 'Sentinel-1' | 'Sentinel-2';
  product_type: string | null;
  product_level: string | null;
  source_filename: string;
  storage_reference: string;
  crs: string | null;
  transform: number[] | null;
  width: number;
  height: number;
  pixel_size_x: number | null;
  pixel_size_y: number | null;
  resolution_x: number | null;
  resolution_y: number | null;
  band_count: number;
  band_names: (string | null)[] | null;
  band_descriptions: (string | null)[] | null;
  band_dtypes: string[] | null;
  nodata_values: (number | null)[] | null;
  mask_flags: string[][] | null;
  has_validity_mask: boolean;
  bounds: [number, number, number, number] | null;
  polarization: string[] | null;
  acquisition_mode: string | null;
  orbit_direction: string | null;
  relative_orbit: number | null;
  processing_baseline: string | null;
  native_band_resolutions: Record<string, number> | null;
  acquisition_metadata: Record<string, unknown> | null;
  product_metadata: Record<string, unknown> | null;
  uploaded_at: string;
  registered_at: string;
  size_bytes: number;
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
  /** Text the annotator submitted, when it differed (an alias). */
  submitted_class_name?: string | null;
  iteration: number;
  version: number;
  /** Durable query item this version answered, when it came from one. */
  query_batch_id?: number | null;
  query_item_id?: number | null;
  /** 'query' only when the stored link says so; never inferred. */
  provenance?: 'manual' | 'query';
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
  evaluation_details: string | null;
  resolution: string;
  evaluation_strategy: string | null;
  n_train: number | null;
  n_test: number | null;
  held_out_groups: number | null;
  per_class_iou: Record<string, number>;
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
  geo_coords: { bbox?: number[]; center?: number[]; crs?: string | null } | null;
  prediction: string | null;
  confidence: number | null;
  uncertainty: number | null;
}

export interface RsalQueryPool {
  size: number;
  hash: string;
  patch_size: number;
  stride: number;
  grid: { rows: number; cols: number };
  grid_cells: number;
  n_labeled_patches: number;
  exclude_labeled: boolean;
  eligibility: string;
}

export interface RsalQueryResponse {
  batch_id: number;
  strategy: string;
  method: string | null;
  strategy_version?: string;
  seed: number | null;
  batch_size: number;
  requested_size?: number | null;
  model_iteration: number | null;
  training_run_id?: number | null;
  dataset_id?: number | null;
  created_at?: string | null;
  pool?: RsalQueryPool | null;
  notes: string[];
  samples: RsalQuerySample[];
}

/** A selected sample inside a durable batch, with its recorded decision. */
export interface RsalQueryItem {
  id: number;
  position: number;
  sample_id: string;
  dataset_id: number;
  row: number;
  col: number;
  coords: RsalQuerySample['coords'];
  geo_coords: RsalQuerySample['geo_coords'];
  score: number | null;
  uncertainty: number | null;
  prediction: string | null;
  confidence: number | null;
  status: 'pending' | 'labeled' | 'rejected' | 'deferred';
  decided_class: string | null;
  decided_at: string | null;
  decision_note: string | null;
  label_id: number | null;
}

export interface RsalQueryBatch {
  id: number;
  project_id: number;
  dataset_id: number | null;
  strategy: string;
  method: string | null;
  strategy_version: string;
  seed: number | null;
  batch_size_requested: number;
  batch_size_returned: number;
  pool: RsalQueryPool | null;
  parameters: Record<string, unknown>;
  model_iteration: number | null;
  training_run_id: number | null;
  notes: string[];
  note: string | null;
  created_at: string;
  decisions: Record<string, number>;
  items?: RsalQueryItem[];
}

/** A run as listed by `/runs`, with its lineage pointer. */
export interface RsalRunSummary extends RsalMetrics {
  manifest_hash?: string | null;
  lineage_status?: 'legacy' | 'incomplete' | 'complete';
  experiment_id?: number | null;
  checkpoint_sha256?: string | null;
}

export interface RsalRunLineage {
  run_id: number;
  iteration: number;
  experiment_id: number | null;
  lineage_status: 'legacy' | 'incomplete' | 'complete';
  manifest: Record<string, unknown> | null;
  manifest_hash: string | null;
  missing: string[];
  artifact: {
    verified?: boolean;
    sha256?: string;
    reason?: string;
    path_name?: string;
  } | null;
  notes: string[];
}

export interface RsalComparisonRow {
  run_id: number;
  iteration: number;
  model_type: string;
  accuracy: number | null;
  f1_macro: number | null;
  n_samples: number;
  evaluation: string | null;
  lineage_status: 'legacy' | 'incomplete' | 'complete';
  manifest_hash: string | null;
  label_snapshot_hash: string | null;
  input_hashes: Record<string, string | null>;
  config: Record<string, unknown>;
  environment_revision: string | null;
}

export interface RsalComparison {
  experiment_id: number | null;
  project_id: number;
  runs: RsalComparisonRow[];
  differences: Record<string, unknown[]>;
  comparable: boolean;
  caveats: string[];
}

export interface RsalExperiment {
  id: number;
  project_id: number;
  name: string;
  description: string;
  hypothesis: string | null;
  config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  run_ids: number[];
}

export interface RsalTrainResponse {
  id: number;
  project_id: number;
  iteration: number;
  model_type: string;
  resolution: string;
  checkpoint: string;
  n_samples: number;
  metrics: RsalMetrics;
}

export interface RsalMapField {
  layer: 'hard' | 'uncertainty' | 'binary';
  method: string | null;
  project_id: number;
  dataset_id: number;
  model_iteration: number;
  training_run_id: number;
  classes: string[];
  resolution: 'pixel' | 'patch';
  binary?: RsalBinarySummary | null;
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
  /** Provenance of the numbers: which raster, which model, what was masked. */
  band_schema_verified?: boolean;
  band_schema_reason?: string | null;
  study_area_applied?: boolean;
  study_area_note?: string | null;
  exports: Record<string, string>;
}

export interface RsalLabelBatchResponse {
  labels: RsalLabel[];
  training: RsalTrainResponse | null;
  training_error: string | null;
}
