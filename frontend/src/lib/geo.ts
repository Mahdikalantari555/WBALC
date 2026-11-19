/**
 * Small, dependency-free geometry helpers shared by the adapter and the browser.
 *
 * RSAL stores each dataset on its own native grid and never reprojects, so every
 * conversion here is pure arithmetic on the stored affine. No libproj, no
 * implicit alignment: a missing CRS or a rotated affine is reported, not guessed.
 */
export type Affine = [number, number, number, number, number, number];
export type XY = [number, number];
export type Bounds = [number, number, number, number];

/** Apply a GDAL-style affine `[a, b, c, d, e, f]` to a pixel position. */
export function applyAffine(transform: number[], col: number, row: number): XY {
  const [a, b, c, d, e, f] = transform;
  return [a * col + b * row + c, d * col + e * row + f];
}

export function invertAffine(transform: number[]): Affine | null {
  const [a, b, c, d, e, f] = transform;
  const det = a * e - b * d;
  if (!Number.isFinite(det) || Math.abs(det) < 1e-14) return null;
  // Inverse of the 2x2 linear part, then the translated origin.
  const ia = e / det;
  const ib = -b / det;
  const id = -d / det;
  const ie = a / det;
  return [ia, ib, -(ia * c + ib * f), id, ie, -(id * c + ie * f)];
}

export function mapToPixel(transform: number[], x: number, y: number): XY | null {
  const inverse = invertAffine(transform);
  if (!inverse) return null;
  const [a, b, c, d, e, f] = inverse;
  return [a * x + b * y + c, d * x + e * y + f];
}

/** True when rotation/skew terms are zero, i.e. north-up and axis-aligned. */
export function isAxisAligned(transform: number[] | null | undefined): boolean {
  return !!transform && transform[1] === 0 && transform[3] === 0;
}

export interface GeoContext {
  crsCode: string | null;
  transform: number[] | null;
  width: number;
  height: number;
}

export type GeorefReason = 'not-georeferenced' | 'unsupported-crs' | 'non-axis-aligned';

/** WGS84 ellipsoid constants for the transverse-Mercator inverse. */
const WGS84_A = 6378137;
const WGS84_F = 1 / 298.257223563;
const WGS84_E2 = WGS84_F * (2 - WGS84_F);
const UTM_K0 = 0.9996;

interface UtmZone {
  zone: number;
  south: boolean;
}

/**
 * Parse the UTM EPSG codes we understand.
 *
 * 326xx = WGS84 north, 327xx = WGS84 south, 269xx = NAD83 north. NAD83 is
 * treated as WGS84: the datums differ by well under a metre, which is far below
 * the pixel size of any Sentinel product, and pretending otherwise would need a
 * full datum-shift table this example deliberately does not ship.
 */
export function parseUtm(crs: string | null | undefined): UtmZone | null {
  const code = normalizeCrs(crs);
  const match = code ? /^EPSG:(326|327|269)(\d{2})$/.exec(code) : null;
  if (!match) return null;
  const zone = Number(match[2]);
  if (zone < 1 || zone > 60) return null;
  return { zone, south: match[1] === '327' };
}

/** Transverse-Mercator (UTM) inverse: easting/northing -> lon/lat in degrees. */
export function utmToLonLat({ zone, south }: UtmZone, easting: number, northing: number): XY {
  // Radius of the meridian arc and the footpoint latitude series.
  const e2 = WGS84_E2;
  const ep2 = e2 / (1 - e2);
  const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
  const x = easting - 500000;
  const y = south ? northing - 10000000 : northing;
  const m = y / UTM_K0;
  const mu =
    m / (WGS84_A * (1 - e2 / 4 - (3 * e2 ** 2) / 64 - (5 * e2 ** 3) / 256));
  const phi1 =
    mu +
    ((3 * e1) / 2 - (27 * e1 ** 3) / 32) * Math.sin(2 * mu) +
    ((21 * e1 ** 2) / 16 - (55 * e1 ** 4) / 32) * Math.sin(4 * mu) +
    ((151 * e1 ** 3) / 96) * Math.sin(6 * mu) +
    ((1097 * e1 ** 4) / 512) * Math.sin(8 * mu);
  const sinPhi = Math.sin(phi1);
  const cosPhi = Math.cos(phi1);
  const tanPhi = Math.tan(phi1);
  const c1 = ep2 * cosPhi ** 2;
  const t1 = tanPhi ** 2;
  const n1 = WGS84_A / Math.sqrt(1 - e2 * sinPhi ** 2);
  const r1 = (WGS84_A * (1 - e2)) / (1 - e2 * sinPhi ** 2) ** 1.5;
  const d = x / (n1 * UTM_K0);
  const lat =
    phi1 -
    ((n1 * tanPhi) / r1) *
      (d ** 2 / 2 -
        ((5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4) / 24 +
        ((61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6) / 720);
  const lon0 = ((zone - 1) * 6 - 180 + 3) * (Math.PI / 180);
  const lon =
    lon0 +
    (d -
      ((1 + 2 * t1 + c1) * d ** 3) / 6 +
      ((5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5) / 120) /
      cosPhi;
  return [(lon * 180) / Math.PI, (lat * 180) / Math.PI];
}

/**
 * Decide whether a dataset can be drawn on a WGS84 basemap.
 *
 * Only 4326 and 3857 are handled without a projection library; anything else is
 * drawn in pixel space (Leaflet `CRS.Simple`) rather than silently misplaced.
 */
export function assessGeoreferencing(ctx: GeoContext): { mode: 'map' | 'pixel'; reason: GeorefReason | null } {
  if (!ctx.transform || ctx.transform.length < 6) {
    return { mode: 'pixel', reason: 'not-georeferenced' };
  }
  if (!isAxisAligned(ctx.transform)) return { mode: 'pixel', reason: 'non-axis-aligned' };
  const code = normalizeCrs(ctx.crsCode);
  if (code !== 'EPSG:4326' && code !== 'EPSG:3857' && !parseUtm(code)) {
    return { mode: 'pixel', reason: 'unsupported-crs' };
  }
  return { mode: 'map', reason: null };
}

export function normalizeCrs(crs: string | null | undefined): string | null {
  if (!crs) return null;
  const trimmed = crs.trim();
  const epsg = /^epsg:(\d+)$/i.exec(trimmed);
  if (epsg) return `EPSG:${epsg[1]}`;
  return trimmed.toUpperCase();
}

/** Projected (EPSG:3857) -> WGS84 for a Web-Mercator raster. */
function mercatorToWgs84([x, y]: XY): XY {
  const lon = (x / 20037508.342789244) * 180;
  let lat = (y / 20037508.342789244) * 180;
  lat = (180 / Math.PI) * (2 * Math.atan(Math.exp((lat * Math.PI) / 180)) - Math.PI / 2);
  return [lon, lat];
}

/** Convert a dataset-CRS coordinate to WGS84, or null when unsupported. */
export function toWgs84(ctx: GeoContext, x: number, y: number): XY | null {
  const code = normalizeCrs(ctx.crsCode);
  if (code === 'EPSG:4326') return [x, y];
  if (code === 'EPSG:3857') return mercatorToWgs84([x, y]);
  const utm = parseUtm(code);
  if (utm) return utmToLonLat(utm, x, y);
  return null;
}

/** WGS84 [west, south, east, north] for the dataset corners. */
export function datasetBounds(ctx: GeoContext): Bounds | null {
  if (assessGeoreferencing(ctx).mode !== 'map') return null;
  const t = ctx.transform!;
  const corners = [
    applyAffine(t, 0, 0),
    applyAffine(t, ctx.width, 0),
    applyAffine(t, 0, ctx.height),
    applyAffine(t, ctx.width, ctx.height),
  ]
    .map(([x, y]) => toWgs84(ctx, x, y))
    .filter((p): p is XY => p !== null);
  if (corners.length !== 4) return null;
  const xs = corners.map((c) => c[0]);
  const ys = corners.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export interface PixelWindow {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export function clampWindow(window: PixelWindow, width: number, height: number): PixelWindow {
  const x0 = Math.max(0, Math.min(width, Math.floor(window.x0)));
  const y0 = Math.max(0, Math.min(height, Math.floor(window.y0)));
  return {
    x0,
    y0,
    x1: Math.max(x0 + 1, Math.min(width, Math.ceil(window.x1))),
    y1: Math.max(y0 + 1, Math.min(height, Math.ceil(window.y1))),
  };
}

/** Pixel window covered by a prediction cell, in source pixels. */
export function cellWindow(
  grid: { patchSize: number; stride: number; region: PixelWindow },
  row: number,
  col: number,
  width: number,
  height: number,
): PixelWindow {
  const x0 = grid.region.x0 + col * grid.stride;
  const y0 = grid.region.y0 + row * grid.stride;
  return clampWindow(
    { x0, y0, x1: x0 + grid.patchSize, y1: y0 + grid.patchSize },
    width,
    height,
  );
}

/** Signed ring area (shoelace) used both for winding and for km² estimates. */
export function ringArea(ring: XY[]): number {
  let total = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    total += x1 * y2 - x2 * y1;
  }
  return total / 2;
}

/**
 * Rough area in km² for a lon/lat ring: planar shoelace scaled by the local
 * metres-per-degree at the ring's mean latitude. Deliberately labelled
 * "approximate" wherever it is shown — it is not a geodesic computation.
 */
export function approximateAreaKm2(ring: XY[]): number | null {
  if (ring.length < 3) return null;
  const meanLat = ring.reduce((sum, [, y]) => sum + y, 0) / ring.length;
  const mPerDegLat = 111_320;
  const mPerDegLon = 111_320 * Math.cos((meanLat * Math.PI) / 180);
  const area = Math.abs(ringArea(ring)) * mPerDegLat * mPerDegLon;
  return Number.isFinite(area) ? area / 1_000_000 : null;
}
