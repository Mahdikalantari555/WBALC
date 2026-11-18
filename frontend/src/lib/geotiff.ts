import { fromArrayBuffer, fromUrl, type GeoTIFF, type GeoTIFFImage } from 'geotiff';
import proj4 from 'proj4';
import type { BandMode, Bounds, RasterMetadata } from '@/types';
import type { PixelWindow } from '@/lib/geo';

function projection(code: number): string | null {
  if (code === 4326) return 'EPSG:4326';
  if (code === 3857) return 'EPSG:3857';
  if (code >= 32601 && code <= 32660)
    return `+proj=utm +zone=${code - 32600} +datum=WGS84 +units=m +no_defs`;
  if (code >= 32701 && code <= 32760)
    return `+proj=utm +zone=${code - 32700} +south +datum=WGS84 +units=m +no_defs`;
  if (code >= 26901 && code <= 26923)
    return `+proj=utm +zone=${code - 26900} +datum=NAD83 +units=m +no_defs`;
  return null;
}

// ------------------------------------------------------------ dataset handles
/** Parsed GeoTIFF + its stretch window, cached per dataset (LRU, cap 3). */
interface DatasetHandle {
  image: GeoTIFFImage;
  /** [lo, hi] percentile range per band index, computed once per dataset. */
  stretch: Map<number, [number, number]>;
}

const handles = new Map<string, Promise<DatasetHandle>>();
const HANDLE_CAP = 3;

/** Drop cached handles (dataset switch, deletion, or explicit refresh). */
export function forgetDataset(datasetId?: string) {
  if (datasetId === undefined) handles.clear();
  else handles.delete(datasetId);
}

async function loadHandle(url: string, datasetId: string): Promise<DatasetHandle> {
  const cached = handles.get(datasetId);
  if (cached) {
    // Refresh LRU order.
    handles.delete(datasetId);
    handles.set(datasetId, cached);
    return cached;
  }
  const promise = (async () => {
    // `fromUrl` issues HTTP Range requests, so opening a scene costs a few KB
    // and a thumbnail costs only the compressed tiles that cover its window.
    const tiff: GeoTIFF = await fromUrl(url, { allowFullFile: true, maxRanges: 4 });
    return { image: await tiff.getImage(), stretch: new Map<number, [number, number]>() };
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
    // Servers without range support (or a file URL) still work: read it whole.
    const response = await fetch(url).catch(() => null);
    if (!response?.ok) throw error;
    const tiff = await fromArrayBuffer(await response.arrayBuffer());
    const fallback = { image: await tiff.getImage(), stretch: new Map<number, [number, number]>() };
    handles.set(datasetId, Promise.resolve(fallback));
    return fallback;
  }
}

/**
 * Percentile stretch for every band, sampled once per dataset.
 *
 * Sampled rather than exact: a full low-resolution read would still have to
 * fetch every block of the scene, which defeats the point of windowed reads on a
 * large GeoTIFF. Six spread windows give a stable stretch at a tiny cost.
 */
async function ensureStretch(handle: DatasetHandle): Promise<Map<number, [number, number]>> {
  if (handle.stretch.size) return handle.stretch;
  const image = handle.image;
  const bandCount = image.getSamplesPerPixel();
  const width = image.getWidth();
  const height = image.getHeight();
  const patch = Math.max(8, Math.min(256, Math.floor(Math.min(width, height) / 4)));
  const anchors: [number, number][] = [
    [0, 0],
    [width - patch, 0],
    [0, height - patch],
    [width - patch, height - patch],
    [Math.floor((width - patch) / 2), Math.floor((height - patch) / 2)],
  ];
  const noData = image.getGDALNoData();
  const samples: number[][] = Array.from({ length: bandCount }, () => []);
  for (const [x, y] of anchors) {
    const raster = await image.readRasters({
      samples: Array.from({ length: bandCount }, (_, b) => b),
      window: [x, y, x + patch, y + patch],
      interleave: false,
    });
    raster.forEach((band, index) => {
      const arr = band as ArrayLike<number>;
      const step = Math.max(1, Math.floor(arr.length / 2048));
      for (let i = 0; i < arr.length; i += step) {
        const value = Number(arr[i]);
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

export async function readMetadata(buffer: ArrayBuffer): Promise<RasterMetadata> {
  const tiff = await fromArrayBuffer(buffer);
  const image = await tiff.getImage();
  const keys = image.getGeoKeys();
  const code = Number(keys?.ProjectedCSTypeGeoKey ?? keys?.GeographicTypeGeoKey ?? 0);
  let bounds: Bounds | null = null;
  let resolution = 'Unknown';
  try {
    const raw = image.getBoundingBox();
    const from = projection(code);
    if (from) {
      const a = proj4(from, 'EPSG:4326', [raw[0], raw[1]]);
      const b = proj4(from, 'EPSG:4326', [raw[2], raw[3]]);
      if ([...a, ...b].every(Number.isFinite)) bounds = [a[0], a[1], b[0], b[1]];
    }
  } catch {
    /* A non-georeferenced TIFF can still be inspected. */
  }
  try {
    const r = image.getResolution();
    resolution = `${Math.abs(r[0]).toLocaleString('en', { maximumFractionDigits: 6 })} ${code === 4326 ? '°' : 'm'}`;
  } catch {
    /* No affine resolution. */
  }
  return {
    bands: image.getSamplesPerPixel(),
    width: image.getWidth(),
    height: image.getHeight(),
    resolution,
    crs: code ? `EPSG:${code}` : 'Not georeferenced',
    bounds,
  };
}

// --------------------------------------------------------------- band mapping
function channelsFor(
  mode: BandMode,
  bandCount: number,
  custom: [number, number, number],
): { channels: number[]; red: number; nir: number } {
  const red = bandCount >= 8 ? 3 : 0;
  const nir = bandCount >= 8 ? 7 : 3;
  if (mode === 'false-color') {
    if (bandCount < 4)
      throw new Error('False color needs at least four spectral bands, including near-infrared.');
    return { channels: [nir, red, bandCount >= 8 ? 2 : 1], red, nir };
  }
  if (mode === 'ndvi') {
    if (bandCount < 4) throw new Error('NDVI requires red and near-infrared bands.');
    return { channels: [red, nir], red, nir };
  }
  if (mode === 'custom')
    return {
      channels: custom.map((v) => Math.min(bandCount - 1, Math.max(0, v))),
      red,
      nir,
    };
  return { channels: bandCount >= 8 ? [3, 2, 1] : bandCount >= 3 ? [0, 1, 2] : [0, 0, 0], red, nir };
}

/**
 * Read exactly `window` pixels from the dataset and paint them into a PNG.
 * This is the review thumbnail path: no scaling maths, no CSS positioning — the
 * pixels returned are the pixels the model classified.
 */
export async function renderPatch(
  url: string,
  datasetId: string,
  window: PixelWindow,
  mode: BandMode = 'true-color',
  custom: [number, number, number] = [0, 1, 2],
  size = 96,
): Promise<string> {
  const handle = await loadHandle(url, datasetId);
  const image = handle.image;
  const bandCount = image.getSamplesPerPixel();
  const { channels, red, nir } = channelsFor(mode, bandCount, custom);
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

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas rendering is unavailable in this browser.');
  const pixels = ctx.createImageData(width, height);
  const noData = image.getGDALNoData();

  for (let i = 0; i < width * height; i++) {
    const base = i * 4;
    const value = Number(arrays[unique.indexOf(channels[0])][i]);
    if (!Number.isFinite(value) || (noData !== null && value === noData)) {
      pixels.data[base + 3] = 0;
      continue;
    }
    if (mode === 'ndvi') {
      const r = Number(arrays[unique.indexOf(red)][i]);
      const n = Number(arrays[unique.indexOf(nir)][i]);
      const ndvi = n + r === 0 ? 0 : (n - r) / (n + r);
      const v = Math.max(0, Math.min(1, (ndvi + 1) / 2));
      pixels.data[base] = Math.round(225 * (1 - v) + 25 * v);
      pixels.data[base + 1] = Math.round(115 * (1 - v) + 175 * v);
      pixels.data[base + 2] = Math.round(80 * (1 - v) + 72 * v);
    } else {
      channels.forEach((channel, c) => {
        const index = unique.indexOf(channel);
        const [lo, hi] = ranges[index];
        pixels.data[base + c] = Math.round(
          Math.max(0, Math.min(1, (Number(arrays[index][i]) - lo) / (hi - lo || 1))) * 255,
        );
      });
    }
    pixels.data[base + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);

  // Nearest-neighbour upscale so a 32 px patch stays blocky instead of blurring
  // into something that looks like a different place. Edge cells can be narrow,
  // so scale by the smaller side to keep the pixel aspect square.
  const scale = size / Math.max(width, height);
  if (scale > 1) {
    const scaled = document.createElement('canvas');
    scaled.width = Math.max(1, Math.round(width * scale));
    scaled.height = Math.max(1, Math.round(height * scale));
    const sctx = scaled.getContext('2d');
    if (sctx) {
      sctx.imageSmoothingEnabled = false;
      sctx.drawImage(canvas, 0, 0, scaled.width, scaled.height);
      return scaled.toDataURL('image/png');
    }
  }
  return canvas.toDataURL('image/png');
}

/** Whole-scene render used by the map overlay. */
export async function renderRaster(
  source: ArrayBuffer | { url: string; datasetId: string },
  mode: BandMode = 'true-color',
  custom: [number, number, number] = [0, 1, 2],
): Promise<string> {
  const image =
    source instanceof ArrayBuffer
      ? await (await fromArrayBuffer(source)).getImage()
      : (await loadHandle(source.url, source.datasetId)).image;
  const bandCount = image.getSamplesPerPixel();
  const ratio = Math.min(1, 1200 / Math.max(image.getWidth(), image.getHeight()));
  const width = Math.max(1, Math.round(image.getWidth() * ratio));
  const height = Math.max(1, Math.round(image.getHeight() * ratio));
  const { channels, red, nir } = channelsFor(mode, bandCount, custom);
  const unique = [...new Set(channels)];
  const raster = await image.readRasters({ samples: unique, width, height, interleave: false });
  const arrays = unique.map((_, i) => raster[i] as ArrayLike<number>);
  const noData = image.getGDALNoData();
  const ranges = arrays.map((arr) => {
    const values: number[] = [];
    const step = Math.max(1, Math.floor(arr.length / 5000));
    for (let i = 0; i < arr.length; i += step)
      if (Number.isFinite(Number(arr[i])) && arr[i] !== noData) values.push(Number(arr[i]));
    values.sort((a, b) => a - b);
    return [
      values[Math.floor(values.length * 0.02)] ?? 0,
      values[Math.floor(values.length * 0.98)] ?? 255,
    ];
  });
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas rendering is unavailable in this browser.');
  const pixels = ctx.createImageData(width, height);
  for (let i = 0; i < width * height; i++) {
    const base = i * 4;
    const value = Number(arrays[0][i]);
    if (!Number.isFinite(value) || (noData !== null && value === noData)) {
      pixels.data[base + 3] = 0;
      continue;
    }
    if (mode === 'ndvi') {
      const r = Number(arrays[unique.indexOf(red)][i]);
      const n = Number(arrays[unique.indexOf(nir)][i]);
      const ndvi = n + r === 0 ? 0 : (n - r) / (n + r);
      const v = Math.max(0, Math.min(1, (ndvi + 1) / 2));
      pixels.data[base] = Math.round(225 * (1 - v) + 25 * v);
      pixels.data[base + 1] = Math.round(115 * (1 - v) + 175 * v);
      pixels.data[base + 2] = Math.round(80 * (1 - v) + 72 * v);
    } else {
      channels.forEach((channel, c) => {
        const index = unique.indexOf(channel);
        const [lo, hi] = ranges[index];
        pixels.data[base + c] = Math.round(
          Math.max(0, Math.min(1, (Number(arrays[index][i]) - lo) / (hi - lo || 1))) * 255,
        );
      });
    }
    pixels.data[base + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}

export interface DecodedClusterRaster {
  width: number;
  height: number;
  indices: Uint16Array;
  noData: number;
}

export async function decodeClusterRaster(buffer: ArrayBuffer): Promise<DecodedClusterRaster> {
  const tiff = await fromArrayBuffer(buffer);
  const image = await tiff.getImage();
  const ratio = Math.min(1, 1200 / Math.max(image.getWidth(), image.getHeight()));
  const width = Math.max(1, Math.round(image.getWidth() * ratio));
  const height = Math.max(1, Math.round(image.getHeight() * ratio));
  const raster = await image.readRasters({
    samples: [0],
    width,
    height,
    resampleMethod: 'nearest',
    interleave: false,
  });
  const raw = raster[0] as ArrayLike<number>;
  const indices = new Uint16Array(width * height);
  for (let i = 0; i < width * height; i++) indices[i] = Number(raw[i]);
  const gdalNoData = image.getGDALNoData();
  return {
    width,
    height,
    indices,
    noData: gdalNoData != null && Number.isFinite(Number(gdalNoData)) ? Number(gdalNoData) : 65535,
  };
}

export function renderClusterOverlay(
  decoded: DecodedClusterRaster,
  colors: Record<number, [number, number, number]>,
  visibleClusters?: Set<number> | null,
): string {
  const { width, height, indices, noData } = decoded;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas rendering is unavailable in this browser.');
  const pixels = ctx.createImageData(width, height);
  for (let i = 0; i < width * height; i++) {
    const cid = indices[i];
    const base = i * 4;
    if (cid === 65535 || cid === noData || (visibleClusters && !visibleClusters.has(cid))) {
      pixels.data[base + 3] = 0;
      continue;
    }
    const rgb = colors[cid] ?? [56, 142, 112];
    pixels.data[base] = rgb[0];
    pixels.data[base + 1] = rgb[1];
    pixels.data[base + 2] = rgb[2];
    pixels.data[base + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}
