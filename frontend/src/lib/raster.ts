/**
 * Client-side GeoTIFF rendering.
 *
 * The browser reads the *original* bytes through the adapter file route and
 * paints them on a canvas. `fromUrl` issues HTTP Range requests, so opening a
 * scene costs a few KB and a preview costs only the tiles that cover its window;
 * the adapter forwards Range upstream. Nothing here reprojects or resamples the
 * source file for storage — the render is a derived PNG in memory only.
 */
import { fromUrl, type GeoTIFFImage } from 'geotiff';

export type BandMode = 'true-color' | 'false-color' | 'ndvi' | `band:${number}` | `nd:${number}:${number}`;

interface Handle {
  image: GeoTIFFImage;
  mask: () => Promise<GeoTIFFImage | null>;
  stretch: Map<number, [number, number]>;
  stretchRequest?: Promise<Map<number, [number, number]>>;
}

export interface RasterPixelInspection {
  bands: { name: string; value: number | null }[];
  difference: boolean;
  index: number | null;
}

const handles = new Map<string, { datasetId: string; promise: Promise<Handle> }>();
const HANDLE_CAP = 3;

export function forgetRaster(datasetId?: string) {
  if (datasetId === undefined) handles.clear();
  else {
    for (const [key, value] of handles) if (value.datasetId === datasetId) handles.delete(key);
  }
}

async function rasterHandle(tiff: Awaited<ReturnType<typeof fromUrl>>): Promise<Handle> {
  const image = await tiff.getImage();
  let cachedMask: Promise<GeoTIFFImage | null> | undefined;
  return { image, stretch: new Map(), mask: () => cachedMask ??= (async () => {
    const count = await tiff.getImageCount();
    for (let index = 1; index < count; index++) {
      const candidate = await tiff.getImage(index);
      if ((candidate.fileDirectory.NewSubfileType & 4) && candidate.getWidth() === image.getWidth() && candidate.getHeight() === image.getHeight()) return candidate;
    }
    return null;
  })() };
}

async function loadHandle(url: string, datasetId: string): Promise<Handle> {
  // Include the project-scoped URL: dataset IDs are only unique inside a project.
  const key = `${datasetId}\u0000${url}`;
  const cached = handles.get(key);
  if (cached) {
    // Refresh LRU order.
    handles.delete(key);
    handles.set(key, cached);
    return cached.promise;
  }
  // Never silently download a potentially multi-gigabyte TIFF when a proxy
  // ignores Range. Rendering has a server-side, bounded PNG fallback instead.
  const promise = fromUrl(url, { allowFullFile: false, maxRanges: 4 }).then(rasterHandle);
  const entry = { datasetId, promise };
  handles.set(key, entry);
  while (handles.size > HANDLE_CAP) {
    const oldest = handles.keys().next().value;
    if (oldest === undefined) break;
    handles.delete(oldest);
  }
  try {
    return await promise;
  } catch (error) {
    handles.delete(key);
    throw error;
  }
}

export async function inspectRasterPixel(
  url: string, id: string, col: number, row: number, mode: BandMode, names?: string[] | null,
): Promise<RasterPixelInspection> {
  try {
    const handle = await loadHandle(url, id);
    const image = handle.image;
    const bandCount = image.getSamplesPerPixel();
    const view = channelsFor(mode, bandCount, names);
    const samples = [...new Set(view.difference ? [view.nir, view.red] : view.channels)];
    const window = [col, row, col + 1, row + 1];
    const mask = await handle.mask();
    const masked = mask ? Number((await mask.readRasters({ window, samples: [0], interleave: true }))[0]) === 0 : false;
    const values = await image.readRasters({ window, samples, interleave: true });
    const noData = image.getGDALNoData();
    const bands = samples.map((band, index) => {
      const value = Number(values[index]);
      return { name: names?.[band] || `#${band + 1}`, value: masked || !Number.isFinite(value) || value === noData ? null : value };
    });
    const [a, b] = bands;
    const index = view.difference && a?.value != null && b?.value != null && a.value + b.value !== 0 ? (a.value - b.value) / (a.value + b.value) : null;
    return { bands, difference: view.difference, index };
  } catch (error) {
    forgetRaster(id);
    try {
      return await backendPixel(url, col, row, mode);
    } catch (fallbackError) {
      throw new Error(`${describe(error)}. ${describe(fallbackError)}`);
    }
  }
}

/**
 * Sampled 2–98% stretch per band, computed once per dataset.
 *
 * Sampled rather than exact on purpose: an exact low-resolution read would still
 * touch every block of the scene, which defeats windowed reads on a large
 * GeoTIFF. Five spread windows give a stable stretch for a tiny cost.
 */
function ensureStretch(handle: Handle) {
  handle.stretchRequest ??= readStretch(handle).catch(error => {
    handle.stretchRequest = undefined;
    throw error;
  });
  return handle.stretchRequest;
}

async function readStretch(handle: Handle): Promise<Map<number, [number, number]>> {
  const image = handle.image;
  const bandCount = image.getSamplesPerPixel();
  const width = image.getWidth();
  const height = image.getHeight();
  const patch = Math.max(1, Math.min(256, Math.floor(Math.min(width, height) / 4)));
  const anchors: [number, number][] = [
    [0, 0],
    [Math.max(0, width - patch), 0],
    [0, Math.max(0, height - patch)],
    [Math.max(0, width - patch), Math.max(0, height - patch)],
    [Math.floor((width - patch) / 2), Math.floor((height - patch) / 2)],
  ];
  const noData = image.getGDALNoData();
  const samples: number[][] = Array.from({ length: bandCount }, () => []);
  for (const [x, y] of anchors) {
    const raster = await image.readRasters({
      samples: Array.from({ length: bandCount }, (_, band) => band),
      window: [x, y, x + patch, y + patch],
      interleave: false,
    });
    raster.forEach((band, index) => {
      const array = band as ArrayLike<number>;
      const step = Math.max(1, Math.floor(array.length / 2048));
      for (let i = 0; i < array.length; i += step) {
        const value = Number(array[i]);
        if (Number.isFinite(value) && value !== noData) samples[index].push(value);
      }
    });
  }
  samples.forEach((values, index) => {
    values.sort((a, b) => a - b);
    handle.stretch.set(index, [
      values[Math.floor(values.length * 0.02)] ?? 0,
      values[Math.floor(values.length * 0.98)] ?? 255,
    ]);
  });
  return handle.stretch;
}

export function channelsFor(mode: BandMode, bandCount: number, names?: string[] | null) {
  const normalized = names?.map(name => name.trim().toLowerCase()) ?? [];
  const lookup = (...aliases: string[]) => normalized.findIndex(name => aliases.includes(name));
  const red = lookup('red', 'b04', 'b4');
  const green = lookup('green', 'b03', 'b3');
  const blue = lookup('blue', 'b02', 'b2');
  const nir = lookup('nir', 'nir08', 'nir_08', 'b08', 'b8');
  const valid = (...indices: number[]) => indices.every(i => Number.isInteger(i) && i >= 0 && i < bandCount);
  const fallback = { channels: [0, 0, 0], red: 0, nir: 0, difference: false };
  if (mode.startsWith('band:')) {
    const index = Number(mode.split(':')[1]);
    return valid(index) ? { ...fallback, channels: [index, index, index] } : fallback;
  }
  if (mode.startsWith('nd:')) {
    const [, first, second] = mode.split(':').map(Number);
    return valid(first, second) && first !== second ? { channels: [first, second], red: second, nir: first, difference: true } : fallback;
  }
  if (mode === 'ndvi' && valid(red, nir)) return { channels: [nir, red], red, nir, difference: true };
  if (mode === 'false-color' && valid(nir, red, green)) return { ...fallback, channels: [nir, red, green] };
  if (mode === 'true-color' && valid(red, green, blue)) return { ...fallback, channels: [red, green, blue] };
  return fallback;
}

function paint(
  image: GeoTIFFImage,
  arrays: ArrayLike<number>[],
  unique: number[],
  channels: number[],
  red: number,
  nir: number,
  difference: boolean,
  ranges: [number, number][],
  width: number,
  height: number,
  water = false,
): string {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas rendering is unavailable in this browser.');
  const pixels = ctx.createImageData(width, height);
  const noData = image.getGDALNoData();
  const index = (band: number) => unique.indexOf(band);
  for (let i = 0; i < width * height; i++) {
    const base = i * 4;
    if (arrays.some(band => !Number.isFinite(band[i]) || (noData !== null && band[i] === noData))) {
      pixels.data[base + 3] = 0;
      continue;
    }
    if (difference) {
      const r = Number(arrays[index(red)]?.[i]);
      const n = Number(arrays[index(nir)]?.[i]);
      if (n + r === 0) continue;
      const ndvi = (n - r) / (n + r);
      const v = Math.max(0, Math.min(1, (ndvi + 1) / 2));
      // High values read as vegetation (green ramp) or water (blue ramp) —
      // the ramp follows the semantic of the index, not the user's choice.
      const [lowC, highC] = water ? WATER_RAMP : VEGETATION_RAMP;
      pixels.data[base] = Math.round(lowC[0] * (1 - v) + highC[0] * v);
      pixels.data[base + 1] = Math.round(lowC[1] * (1 - v) + highC[1] * v);
      pixels.data[base + 2] = Math.round(lowC[2] * (1 - v) + highC[2] * v);
    } else {
      channels.forEach((channel, c) => {
        const at = index(channel);
        const [lo, hi] = ranges[at] ?? [0, 255];
        const raw = Number(arrays[at]?.[i]);
        const scaled = Math.max(0, Math.min(1, (raw - lo) / (hi - lo || 1)));
        pixels.data[base + c] = Math.round(scaled * 255);
      });
    }
    pixels.data[base + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}

/** Land → green vegetation ramp for the generic normalized-difference views. */
const VEGETATION_RAMP: [number, number, number][] = [[225, 115, 80], [25, 175, 72]];
/** Land → open-water ramp for green-based indices (NDWI, MNDWI). */
const WATER_RAMP: [number, number, number][] = [[225, 115, 80], [25, 110, 175]];

/**
 * Water indices put green first: (green − nir) / (green + nir) and its SWIR
 * variant. Any other pair keeps the vegetation ramp.
 */
function isWaterDifference(mode: BandMode, names?: string[] | null): boolean {
  if (!mode.startsWith('nd:') || !names?.length) return false;
  const [, first, second] = mode.split(':').map(Number);
  const normalized = names.map(name => (name ?? '').trim().toLowerCase());
  const at = (i: number) => normalized[i] ?? '';
  const highIsWater = ['nir08', 'nir_08', 'b08', 'b8', 'swir16', 'swir_16', 'b11', 'swir22', 'swir_22', 'b12'];
  return at(first) === 'green' && highIsWater.includes(at(second));
}

async function backendPreview(
  url: string,
  mode: BandMode,
  size: number,
  window?: { x0: number; y0: number; x1: number; y1: number },
): Promise<string> {
  const endpoint = url.replace(/\/file(?:\?.*)?$/, '/preview');
  if (endpoint === url) throw new Error('No server-side preview route is available for this raster.');
  const query = new URLSearchParams({ mode, size: String(size) });
  if (window) {
    query.set('x0', String(window.x0)); query.set('y0', String(window.y0));
    query.set('x1', String(window.x1)); query.set('y1', String(window.y1));
    query.set('upscale', 'true');
  }
  const response = await fetch(`${endpoint}?${query}`, { headers: { accept: 'image/png' } });
  if (!response.ok) {
    const failure = await response.json().catch(() => null) as { message?: unknown } | null;
    throw new Error(typeof failure?.message === 'string' ? failure.message : `Server preview failed (${response.status}).`);
  }
  if (!response.headers.get('content-type')?.toLowerCase().includes('image/png')) {
    throw new Error('The server returned an invalid raster preview.');
  }
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Could not read the raster preview.'));
    reader.onerror = () => reject(new Error('Could not read the raster preview.'));
    reader.readAsDataURL(blob);
  });
}

async function backendPixel(
  url: string,
  x: number,
  y: number,
  mode: BandMode,
): Promise<RasterPixelInspection> {
  const endpoint = url.replace(/\/file(?:\?.*)?$/, '/pixel');
  if (endpoint === url) throw new Error('No server-side pixel probe is available for this raster.');
  const query = new URLSearchParams({ mode, x: String(x), y: String(y) });
  const response = await fetch(`${endpoint}?${query}`, { headers: { accept: 'application/json' } });
  const result: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = result && typeof result === 'object' ? (result as { message?: unknown }).message : null;
    throw new Error(typeof message === 'string' ? message : `Server pixel probe failed (${response.status}).`);
  }
  if (!result || typeof result !== 'object') throw new Error('The server returned an invalid pixel probe.');
  const probe = result as Record<string, unknown>;
  if (!Array.isArray(probe.bands) || typeof probe.difference !== 'boolean' ||
      !(probe.index === null || typeof probe.index === 'number')) {
    throw new Error('The server returned an invalid pixel probe.');
  }
  return probe as unknown as RasterPixelInspection;
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Whole-scene preview, capped so a huge scene does not exhaust canvas memory. */
export async function renderRaster(
  url: string,
  datasetId: string,
  mode: BandMode = 'true-color',
  maxSize = 1400,
  names?: string[] | null,
): Promise<string> {
  try {
    const handle = await loadHandle(url, datasetId);
    const image = handle.image;
    const ratio = Math.min(1, maxSize / Math.max(image.getWidth(), image.getHeight()));
    const width = Math.max(1, Math.round(image.getWidth() * ratio));
    const height = Math.max(1, Math.round(image.getHeight() * ratio));
    const bandCount = image.getSamplesPerPixel();
    const { channels, red, nir, difference } = channelsFor(mode, bandCount, names);
    const unique = [...new Set(channels)];
    const stretch = await ensureStretch(handle);
    const ranges = unique.map((band) => stretch.get(band) ?? ([0, 255] as [number, number]));
    const raster = await image.readRasters({ samples: unique, width, height, interleave: false });
    const arrays = unique.map((_, i) => raster[i] as ArrayLike<number>);
    return paint(image, arrays, unique, channels, red, nir, difference, ranges, width, height, isWaterDifference(mode, names));
  } catch (error) {
    forgetRaster(datasetId);
    try {
      return await backendPreview(url, mode, maxSize);
    } catch (fallbackError) {
      throw new Error(`${describe(error)}. ${describe(fallbackError)}`);
    }
  }
}

/** Exact-window render used by review thumbnails: no CSS scaling, real pixels. */
export async function renderWindow(
  url: string,
  datasetId: string,
  window: { x0: number; y0: number; x1: number; y1: number },
  mode: BandMode = 'true-color',
  size = 128,
  names?: string[] | null,
): Promise<string> {
  try {
    const handle = await loadHandle(url, datasetId);
    const image = handle.image;
    const bandCount = image.getSamplesPerPixel();
    const { channels, red, nir, difference } = channelsFor(mode, bandCount, names);
    const unique = [...new Set(channels)];
    const width = Math.max(1, Math.round(window.x1 - window.x0));
    const height = Math.max(1, Math.round(window.y1 - window.y0));
    const stretch = await ensureStretch(handle);
    const ranges = unique.map((band) => stretch.get(band) ?? ([0, 255] as [number, number]));
    const raster = await image.readRasters({
      samples: unique,
      window: [window.x0, window.y0, window.x1, window.y1],
      interleave: false,
    });
    const arrays = unique.map((_, i) => raster[i] as ArrayLike<number>);
    const dataUrl = paint(image, arrays, unique, channels, red, nir, difference, ranges, width, height);

    // Nearest-neighbour upscale so a 32px patch stays blocky rather than blurring
    // into something that looks like a different place.
    const scale = size / Math.max(width, height);
    if (scale <= 1) return dataUrl;
    const scaled = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('Could not decode the rendered preview.'));
      img.src = dataUrl;
    });
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const ctx = canvas.getContext('2d');
    if (!ctx) return dataUrl;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(scaled, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/png');
  } catch (error) {
    forgetRaster(datasetId);
    try {
      return await backendPreview(url, mode, size, window);
    } catch (fallbackError) {
      throw new Error(`${describe(error)}. ${describe(fallbackError)}`);
    }
  }
}

/**
 * Binary water mask → transparent PNG data URL (blue where water). The grid is
 * the scene's own pixel grid, so the overlay aligns with the imagery exactly.
 */
export function renderWaterOverlay(values: (number | null)[][], color = 'rgb(30, 120, 200)'): string {
  const height = values.length;
  const width = height ? values[0].length : 0;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas rendering is unavailable in this browser.');
  const pixels = ctx.createImageData(width, height);
  const [r, g, b] = color.match(/\d+/g)?.map(Number) ?? [30, 120, 200];
  for (let row = 0; row < height; row++) {
    for (let col = 0; col < width; col++) {
      if (values[row]?.[col] !== 1) continue;
      const base = (row * width + col) * 4;
      pixels.data[base] = r;
      pixels.data[base + 1] = g;
      pixels.data[base + 2] = b;
      pixels.data[base + 3] = 255;
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}

/** CSS gradient for the active normalized-difference legend. */
export function waterIndexRamp(mode: BandMode, names?: string[] | null): { water: boolean; gradient: string } {
  const water = isWaterDifference(mode, names);
  const ramp = water ? WATER_RAMP : VEGETATION_RAMP;
  const gradient = `linear-gradient(to right, rgb(${ramp[0].join(',')}), rgb(${ramp[1].join(',')}))`;
  return { water, gradient };
}
