/**
 * Client-side GeoTIFF rendering.
 *
 * The browser reads the *original* bytes through the adapter file route and
 * paints them on a canvas. `fromUrl` issues HTTP Range requests, so opening a
 * scene costs a few KB and a preview costs only the tiles that cover its window;
 * the adapter forwards Range upstream. Nothing here reprojects or resamples the
 * source file for storage — the render is a derived PNG in memory only.
 */
import { fromArrayBuffer, fromUrl, type GeoTIFFImage } from 'geotiff';

export type BandMode = 'true-color' | 'false-color' | 'ndvi';

interface Handle {
  image: GeoTIFFImage;
  stretch: Map<number, [number, number]>;
}

const handles = new Map<string, Promise<Handle>>();
const HANDLE_CAP = 3;

export function forgetRaster(datasetId?: string) {
  if (datasetId === undefined) handles.clear();
  else handles.delete(datasetId);
}

async function loadHandle(url: string, datasetId: string): Promise<Handle> {
  const cached = handles.get(datasetId);
  if (cached) {
    // Refresh LRU order.
    handles.delete(datasetId);
    handles.set(datasetId, cached);
    return cached;
  }
  const promise = (async () => {
    try {
      const tiff = await fromUrl(url, { allowFullFile: true, maxRanges: 4 });
      return { image: await tiff.getImage(), stretch: new Map<number, [number, number]>() };
    } catch (error) {
      // A host without Range support still works: read the file once.
      const response = await fetch(url).catch(() => null);
      if (!response?.ok) throw error;
      const tiff = await fromArrayBuffer(await response.arrayBuffer());
      return { image: await tiff.getImage(), stretch: new Map<number, [number, number]>() };
    }
  })();
  handles.set(datasetId, promise);
  while (handles.size > HANDLE_CAP) {
    const oldest = handles.keys().next().value;
    if (oldest === undefined) break;
    handles.delete(oldest);
  }
  try {
    return await promise;
  } catch (error) {
    handles.delete(datasetId);
    throw error;
  }
}

/**
 * Sampled 2–98% stretch per band, computed once per dataset.
 *
 * Sampled rather than exact on purpose: an exact low-resolution read would still
 * touch every block of the scene, which defeats windowed reads on a large
 * GeoTIFF. Five spread windows give a stable stretch for a tiny cost.
 */
async function ensureStretch(handle: Handle): Promise<Map<number, [number, number]>> {
  if (handle.stretch.size) return handle.stretch;
  const image = handle.image;
  const bandCount = image.getSamplesPerPixel();
  const width = image.getWidth();
  const height = image.getHeight();
  const patch = Math.max(8, Math.min(256, Math.floor(Math.min(width, height) / 4)));
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

function channelsFor(mode: BandMode, bandCount: number) {
  const red = bandCount >= 8 ? 3 : 0;
  const nir = bandCount >= 8 ? 7 : 3;
  if (mode === 'false-color') {
    if (bandCount < 4) return { channels: [0, 0, 0], red, nir };
    return { channels: [nir, red, bandCount >= 8 ? 2 : 1], red, nir };
  }
  if (mode === 'ndvi') {
    if (bandCount < 4) return { channels: [0, 0], red, nir };
    return { channels: [red, nir], red, nir };
  }
  return { channels: bandCount >= 8 ? [3, 2, 1] : bandCount >= 3 ? [0, 1, 2] : [0, 0, 0], red, nir };
}

function paint(
  image: GeoTIFFImage,
  arrays: ArrayLike<number>[],
  unique: number[],
  channels: number[],
  red: number,
  nir: number,
  mode: BandMode,
  ranges: [number, number][],
  width: number,
  height: number,
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
    const value = Number(arrays[0]?.[i]);
    if (!Number.isFinite(value) || (noData !== null && value === noData)) {
      pixels.data[base + 3] = 0;
      continue;
    }
    if (mode === 'ndvi') {
      const r = Number(arrays[index(red)]?.[i]);
      const n = Number(arrays[index(nir)]?.[i]);
      const ndvi = n + r === 0 ? 0 : (n - r) / (n + r);
      const v = Math.max(0, Math.min(1, (ndvi + 1) / 2));
      pixels.data[base] = Math.round(225 * (1 - v) + 25 * v);
      pixels.data[base + 1] = Math.round(115 * (1 - v) + 175 * v);
      pixels.data[base + 2] = Math.round(80 * (1 - v) + 72 * v);
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

/** Whole-scene preview, capped so a huge scene does not exhaust canvas memory. */
export async function renderRaster(
  url: string,
  datasetId: string,
  mode: BandMode = 'true-color',
  maxSize = 1400,
): Promise<string> {
  const handle = await loadHandle(url, datasetId);
  const image = handle.image;
  const ratio = Math.min(1, maxSize / Math.max(image.getWidth(), image.getHeight()));
  const width = Math.max(1, Math.round(image.getWidth() * ratio));
  const height = Math.max(1, Math.round(image.getHeight() * ratio));
  const bandCount = image.getSamplesPerPixel();
  const { channels, red, nir } = channelsFor(mode, bandCount);
  const unique = [...new Set(channels)];
  const stretch = await ensureStretch(handle);
  const ranges = unique.map((band) => stretch.get(band) ?? ([0, 255] as [number, number]));
  const raster = await image.readRasters({
    samples: unique,
    width,
    height,
    interleave: false,
  });
  const arrays = unique.map((_, i) => raster[i] as ArrayLike<number>);
  return paint(image, arrays, unique, channels, red, nir, mode, ranges, width, height);
}

/** Exact-window render used by review thumbnails: no CSS scaling, real pixels. */
export async function renderWindow(
  url: string,
  datasetId: string,
  window: { x0: number; y0: number; x1: number; y1: number },
  mode: BandMode = 'true-color',
  size = 128,
): Promise<string> {
  const handle = await loadHandle(url, datasetId);
  const image = handle.image;
  const bandCount = image.getSamplesPerPixel();
  const { channels, red, nir } = channelsFor(mode, bandCount);
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
  const dataUrl = paint(image, arrays, unique, channels, red, nir, mode, ranges, width, height);

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
}
