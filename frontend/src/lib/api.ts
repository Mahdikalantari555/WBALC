import type {
  CreateProjectInput,
  Dataset,
  Iteration,
  LabelInput,
  MapExportFormat,
  MapField,
  MapLayer,
  Metrics,
  Project,
  Sample,
  SceneMetadata,
  SceneUploadMetadata,
  SomClassification,
  SomClassifyInput,
  SomData,
  SomQueryOptions,
  UncertaintyMethod,
} from '@/types';
const BASE = '/api/projects';
type RsalScene = {
  id: number;
  project_id: number;
  acquisition_datetime: string | null;
  platform: string | null;
  sensor: SceneMetadata['sensor'];
  product_type: string | null;
  product_level: string | null;
  processing_baseline: string | null;
  native_band_resolutions: Record<string, number> | null;
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
  has_validity_mask: boolean;
  bounds: [number, number, number, number] | null;
  polarization: string[] | null;
  acquisition_mode: string | null;
  orbit_direction: string | null;
  relative_orbit: number | null;
  uploaded_at: string;
  registered_at: string;
  size_bytes: number;
};
function sceneFromApi(scene: RsalScene): SceneMetadata {
  return {
    id: String(scene.id),
    projectId: String(scene.project_id),
    acquisitionDateTime: scene.acquisition_datetime,
    platform: scene.platform,
    sensor: scene.sensor,
    productType: scene.product_type,
    productLevel: scene.product_level,
    processingBaseline: scene.processing_baseline,
    nativeBandResolutions: scene.native_band_resolutions,
    sourceFilename: scene.source_filename,
    crs: scene.crs,
    transform: scene.transform,
    width: scene.width,
    height: scene.height,
    pixelSizeX: scene.pixel_size_x,
    pixelSizeY: scene.pixel_size_y,
    resolutionX: scene.resolution_x,
    resolutionY: scene.resolution_y,
    bandCount: scene.band_count,
    bandNames: scene.band_names,
    bandDescriptions: scene.band_descriptions,
    bandDtypes: scene.band_dtypes,
    nodataValues: scene.nodata_values,
    hasValidityMask: scene.has_validity_mask,
    bounds: scene.bounds,
    polarization: scene.polarization,
    acquisitionMode: scene.acquisition_mode,
    orbitDirection: scene.orbit_direction,
    relativeOrbit: scene.relative_orbit,
    productReference: scene.storage_reference,
    uploadedAt: scene.uploaded_at,
    registeredAt: scene.registered_at,
    sizeBytes: scene.size_bytes,
  };
}
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  const data = await response
    .json()
    .catch(() => ({ error: 'The server returned an unreadable response.' }));
  if (!response.ok)
    throw new Error(
      typeof data.error === 'string'
        ? data.error
        : typeof data.detail === 'string'
          ? data.detail
          : `Request failed (${response.status}).`,
    );
  return data as T;
}
/** Query string for a map-layer request. */
function mapQuery(options: {
  layer: MapLayer;
  method?: UncertaintyMethod;
  datasetId?: string;
  iteration?: number;
}): string {
  const params = new URLSearchParams({ layer: options.layer });
  if (options.layer === 'uncertainty') params.set('method', options.method ?? 'entropy');
  if (options.datasetId) params.set('datasetId', options.datasetId);
  if (options.iteration !== undefined) params.set('iteration', String(options.iteration));
  return params.toString();
}

export const api = {
  projects: () => request<Project[]>(''),
  createProject: (data: CreateProjectInput) =>
    request<Project>('', { method: 'POST', body: JSON.stringify(data) }),
  dataset: (id: string) => request<Dataset[]>(`/${id}/dataset`),
  scenes: async (id: string) =>
    (await request<RsalScene[]>(`/${id}/scenes`)).map(sceneFromApi),
  uploadScene: (id: string, file: File, metadata: SceneUploadMetadata) =>
    new Promise<SceneMetadata>((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      form.append('sensor', metadata.sensor);
      const fields: [keyof SceneUploadMetadata, string][] = [
        ['acquisitionDateTime', 'acquisition_datetime'],
        ['platform', 'platform'],
        ['productType', 'product_type'],
        ['productLevel', 'product_level'],
        ['polarization', 'polarization'],
        ['acquisitionMode', 'acquisition_mode'],
        ['orbitDirection', 'orbit_direction'],
        ['relativeOrbit', 'relative_orbit'],
        ['processingBaseline', 'processing_baseline'],
        ['nativeBandResolutions', 'native_band_resolutions'],
      ];
      for (const [key, name] of fields) {
        const value = metadata[key];
        if (typeof value === 'string' && value.trim()) form.append(name, value.trim());
      }
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/${id}/scenes`);
      xhr.timeout = 180000;
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(sceneFromApi(data as RsalScene));
          else {
            const detail = Array.isArray(data.detail)
              ? data.detail.map((item: { msg?: string }) => item.msg ?? 'Invalid metadata').join('; ')
              : data.detail ?? data.error ?? 'Scene upload failed.';
            reject(new Error(String(detail)));
          }
        } catch {
          reject(new Error('The server returned an invalid scene response.'));
        }
      };
      xhr.onerror = () => reject(new Error('Network error. The scene was not uploaded.'));
      xhr.ontimeout = () => reject(new Error('Scene upload timed out. Try a smaller GeoTIFF.'));
      xhr.send(form);
    }),
  deleteScene: (id: string, sceneId: string) =>
    request<void>(`/${id}/scenes/${sceneId}`, { method: 'DELETE' }),
  savedLabels: (id: string) => request<Sample[]>(`/${id}/labels`),
  metrics: (id: string) => request<Metrics>(`/${id}/metrics`),
  som: (
    id: string,
    params?: { datasetId?: string; rows?: number; cols?: number; epochs?: number },
  ) => {
    const qs = new URLSearchParams();
    if (params?.datasetId) qs.set('datasetId', params.datasetId);
    if (params?.rows) qs.set('rows', String(params.rows));
    if (params?.cols) qs.set('cols', String(params.cols));
    if (params?.epochs) qs.set('epochs', String(params.epochs));
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return request<SomData>(`/${id}/som${suffix}`);
  },
  somClassify: (id: string, input: SomClassifyInput) =>
    request<SomClassification>(`/${id}/som-classify`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  query: (
    id: string,
    batchSize: number,
    strategy: string,
    datasetId?: string,
    options?: SomQueryOptions,
  ) =>
    request<{ samples: Sample[]; existing: boolean }>(`/${id}/query`, {
      method: 'POST',
      body: JSON.stringify({
        batchSize,
        strategy,
        ...(datasetId ? { datasetId } : {}),
        ...(options ?? {}),
      }),
    }),
  labels: (id: string, labels: LabelInput[]) =>
    request<{ saved: number }>(`/${id}/labels`, {
      method: 'POST',
      body: JSON.stringify({ labels }),
    }),
  deleteLabel: (id: string, sampleId: string) =>
    request<{ deleted: boolean }>(`/${id}/labels/${encodeURIComponent(sampleId)}`, {
      method: 'DELETE',
    }),
  train: (id: string) =>
    request<{ iteration: Iteration }>(`/${id}/train`, {
      method: 'POST',
      body: '{}',
    }),
  mapField: (id: string, options: Parameters<typeof mapQuery>[0]) =>
    request<MapField>(`/${id}/map?${mapQuery(options)}`),
  /** Download URL for a layer export; the browser handles the file itself. */
  mapExportUrl: (
    id: string,
    options: {
      layer: MapLayer | 'probability';
      format: MapExportFormat;
      method?: UncertaintyMethod;
      datasetId?: string;
      scale?: number;
    },
  ) => {
    const params = new URLSearchParams({ format: options.format });
    if (options.layer === 'uncertainty') params.set('method', options.method ?? 'entropy');
    if (options.layer === 'probability') params.set('layer', 'probability');
    if (options.datasetId) params.set('datasetId', options.datasetId);
    if (options.scale) params.set('scale', String(options.scale));
    return `${BASE}/${id}/map/export?${params.toString()}`;
  },
  deleteDataset: (id: string, datasetId: string) =>
    request<{ deleted: boolean }>(`/${id}/dataset/${datasetId}`, { method: 'DELETE' }),
  upload: (id: string, file: File, onProgress: (progress: number) => void) =>
    new Promise<Dataset>((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/${id}/upload`);
      xhr.timeout = 180000;
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 95));
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            onProgress(100);
            resolve(data);
          } else reject(new Error(data.error ?? 'Upload failed.'));
        } catch {
          reject(new Error('The server returned an invalid response.'));
        }
      };
      xhr.onerror = () => reject(new Error('Network error. Your file was not uploaded.'));
      xhr.ontimeout = () => reject(new Error('Upload timed out. Try a smaller file.'));
      xhr.send(form);
    }),
};
