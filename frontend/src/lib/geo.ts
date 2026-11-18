/**
 * Shared pixel <-> display transform for the TerraLab workspace.
 *
 * Browser-safe (no Node APIs) so the BFF adapter and the map/thumbnail code use
 * literally the same implementation. A pixel therefore has exactly one meaning
 * everywhere: in the review thumbnail, on the map, and in a submitted label.
 */
import proj4 from 'proj4';
import type { GeorefReason, PixelWindow } from '@/types';

export type { PixelWindow, GeorefReason };

proj4.defs('EPSG:4326', '+proj=longlat +datum=WGS84 +no_defs');
proj4.defs(
  'EPSG:3857',
  '+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +nadgrids=@null +wktext +no_defs',
);

/** The minimum a dataset must expose for coordinate maths. */
export interface GeoContext {
  /** EPSG code or proj4 string when known; null when the raster is not georeferenced. */
  crsCode: string | null;
  /** GDAL-style affine [a, b, c, d, e, f]: x = a*col + b*row + c. */
  transform: number[] | null;
  width: number;
  height: number;
}

/** Affine fit from pixel space to normalised display space (u east, v south). */
export interface OverlayFit {
  /** [a, b, c, d, e, f] mapping (col, row) to (u, v) in 0..1. */
  matrix: number[];
  /** Worst corner residual, in units of the scene span. */
  residual: number;
  /** Scene rotation relative to true north, in degrees. */
  tilt: number;
}

export interface GeorefState {
  /** `map` = WGS84 basemap presentation, `pixel` = Leaflet CRS.Simple. */
  mode: 'map' | 'pixel';
  reason: GeorefReason | null;
  tilt: number;
  fit: OverlayFit | null;
}

/** Build the geo context from a workspace dataset. */
export function datasetGeoContext(dataset: {
  crs: string;
  transform: number[] | null;
  width: number;
  height: number;
}): GeoContext {
  return {
    crsCode: dataset.crs && dataset.crs !== 'Not georeferenced' ? dataset.crs : null,
    transform: dataset.transform,
    width: dataset.width,
    height: dataset.height,
  };
}

/** proj4 definition for the EPSG codes GeoTIFFs commonly carry. */
export function projectionDef(crs: string | null): string | null {
  if (!crs) return null;
  const match = /^EPSG:(\d+)$/i.exec(crs.trim());
  if (!match) return crs.includes('+proj') ? crs : null;
  const code = Number(match[1]);
  if (code === 4326 || code === 3857) return `EPSG:${code}`;
  if (code >= 32601 && code <= 32660)
    return `+proj=utm +zone=${code - 32600} +datum=WGS84 +units=m +no_defs`;
  if (code >= 32701 && code <= 32760)
    return `+proj=utm +zone=${code - 32700} +south +datum=WGS84 +units=m +no_defs`;
  if (code >= 26901 && code <= 26923)
    return `+proj=utm +zone=${code - 26900} +datum=NAD83 +units=m +no_defs`;
  return null;
}

/** GDAL-style affine: x = a*col + b*row + c. */
export function applyAffine(t: number[], col: number, row: number): [number, number] {
  return [t[0] * col + t[1] * row + t[2], t[3] * col + t[4] * row + t[5]];
}

export function invertAffine(t: number[], x: number, y: number): [number, number] {
  const det = t[0] * t[4] - t[1] * t[3];
  if (!det) return [x, y];
  const dx = x - t[2];
  const dy = y - t[5];
  return [(t[4] * dx - t[1] * dy) / det, (-t[3] * dx + t[0] * dy) / det];
}

export function toWgs84(ctx: GeoContext, x: number, y: number): [number, number] | null {
  const def = projectionDef(ctx.crsCode);
  if (!def) return null;
  try {
    const [lng, lat] = proj4(def, 'EPSG:4326', [x, y]);
    return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
  } catch {
    return null;
  }
}

export function fromWgs84(ctx: GeoContext, lng: number, lat: number): [number, number] | null {
  const def = projectionDef(ctx.crsCode);
  if (!def) return null;
  try {
    const [x, y] = proj4('EPSG:4326', def, [lng, lat]);
    return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
  } catch {
    return null;
  }
}

/** True when the dataset transform is north-up (no rotation/shear). */
export function isNorthUp(transform: number[] | null): boolean {
  if (!transform) return false;
  return Math.abs(transform[1]) < 1e-12 && Math.abs(transform[3]) < 1e-12;
}

/** 3x3 linear solve (Gauss-Jordan); returns null if singular. */
function solve3(m: number[][], rhs: number[]): number[] | null {
  const a = m.map((row, i) => [...row, rhs[i]]);
  for (let col = 0; col < 3; col++) {
    let pivot = col;
    for (let row = col + 1; row < 3; row++)
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    if (Math.abs(a[pivot][col]) < 1e-18) return null;
    [a[col], a[pivot]] = [a[pivot], a[col]];
    for (let row = 0; row < 3; row++) {
      if (row === col) continue;
      const factor = a[row][col] / a[col][col];
      for (let k = col; k < 4; k++) a[row][k] -= factor * a[col][k];
    }
  }
  return [a[0][3] / a[0][0], a[1][3] / a[1][1], a[2][3] / a[2][2]];
}

/**
 * Least-squares affine fit from pixel space to normalised display space through
 * the four reprojected corners. The raster overlay paints with this fit and the
 * markers are placed with the same one, so imagery and samples cannot drift
 * apart — including for scenes whose extent is rotated or sheared relative to
 * the map, which a plain north-up `ImageOverlay` gets wrong.
 */
function fitCorners(ctx: GeoContext): OverlayFit | null {
  const t = ctx.transform;
  if (!t) return null;
  const pixels: [number, number][] = [
    [0, 0],
    [ctx.width, 0],
    [0, ctx.height],
    [ctx.width, ctx.height],
  ];
  const projected = pixels
    .map(([col, row]) => applyAffine(t, col, row))
    .map(([x, y]) => toWgs84(ctx, x, y));
  if (projected.some((p) => p === null)) return null;
  const lngs = projected.map((p) => p![0]);
  const lats = projected.map((p) => p![1]);
  const west = Math.min(...lngs);
  const east = Math.max(...lngs);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  const spanX = east - west;
  const spanY = north - south;
  if (!(spanX > 0) || !(spanY > 0)) return null;

  const targets: [number, number][] = projected.map((p) => [
    (p![0] - west) / spanX,
    (north - p![1]) / spanY,
  ]);

  const normal = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  const rhsU = [0, 0, 0];
  const rhsV = [0, 0, 0];
  pixels.forEach(([col, row], i) => {
    const basis = [col, row, 1];
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) normal[r][c] += basis[r] * basis[c];
      rhsU[r] += basis[r] * targets[i][0];
      rhsV[r] += basis[r] * targets[i][1];
    }
  });
  const u = solve3(normal, rhsU);
  const v = solve3(normal, rhsV);
  if (!u || !v) return null;

  const residual = Math.max(
    ...pixels.map(([col, row], i) => {
      const du = u[0] * col + u[1] * row + u[2] - targets[i][0];
      const dv = v[0] * col + v[1] * row + v[2] - targets[i][1];
      return Math.hypot(du, dv);
    }),
  );
  // Rotation of the +col axis in display space, degrees clockwise from east.
  const tilt = (-Math.atan2(u[1], u[0]) * 180) / Math.PI;
  return { matrix: [u[0], u[1], u[2], v[0], v[1], v[2]], residual, tilt };
}

/**
 * How this dataset can be displayed honestly.
 *
 * A scene with a resolvable CRS is drawn on the WGS84 basemap; the overlay is
 * warped by the corner fit, so rotation and shear are compensated rather than
 * tolerated. Only scenes whose reprojection is not affine (unsupported CRS, or a
 * fit residual above `tolerance` of the scene span) fall back to pixel space,
 * where imagery and samples are guaranteed to agree.
 */
export function assessGeoreferencing(ctx: GeoContext, tolerance = 0.02): GeorefState {
  if (!ctx.transform) return { mode: 'pixel', reason: 'not-georeferenced', tilt: 0, fit: null };
  if (!projectionDef(ctx.crsCode))
    return { mode: 'pixel', reason: 'unsupported-crs', tilt: 0, fit: null };
  const fit = fitCorners(ctx);
  if (!fit) return { mode: 'pixel', reason: 'unsupported-crs', tilt: 0, fit: null };
  if (fit.residual > tolerance)
    return { mode: 'pixel', reason: 'non-axis-aligned', tilt: fit.tilt, fit };
  return { mode: 'map', reason: null, tilt: fit.tilt, fit };
}

/**
 * Canvas transform for painting a raster (in source pixel coordinates) into a
 * `width` x `height` canvas laid out over the dataset's display bounding box.
 * Null for pixel-space scenes, whose PNG is already in the display frame.
 */
export function overlayTransform(
  ctx: GeoContext,
  width: number,
  height: number,
): number[] | null {
  const state = assessGeoreferencing(ctx);
  if (state.mode !== 'map' || !state.fit) return null;
  const [a, b, c, d, e, f] = state.fit.matrix;
  return [a * width, b * width, c * width, d * height, e * height, f * height];
}

/** Display-space bounds [w, s, e, n] the icon the overlay is fitted to. */
export function displayBounds(ctx: GeoContext): [number, number, number, number] | null {
  const state = assessGeoreferencing(ctx);
  if (state.mode !== 'map' || !state.fit) return null;
  const t = ctx.transform!;
  const corners = [
    applyAffine(t, 0, 0),
    applyAffine(t, ctx.width, 0),
    applyAffine(t, 0, ctx.height),
    applyAffine(t, ctx.width, ctx.height),
  ]
    .map(([x, y]) => toWgs84(ctx, x, y))
    .filter((p): p is [number, number] => p !== null);
  if (corners.length !== 4) return null;
  const xs = corners.map((c) => c[0]);
  const ys = corners.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/**
 * Pixel coordinates -> display coordinates.
 * Georeferenced: WGS84 lng/lat. Pixel space: x stays lng, lat flips so Leaflet
 * CRS.Simple shows the raster the right way up.
 */
export function pixelToDisplay(
  ctx: GeoContext,
  x: number,
  y: number,
): { lng: number; lat: number } {
  if (assessGeoreferencing(ctx).mode === 'map') {
    const [mx, my] = applyAffine(ctx.transform!, x, y);
    const wgs = toWgs84(ctx, mx, my);
    if (wgs) return { lng: wgs[0], lat: wgs[1] };
  }
  return { lng: x, lat: ctx.height - y };
}

/** Display coordinates -> pixel (col, row). Inverse of `pixelToDisplay`. */
export function displayToPixel(
  ctx: GeoContext,
  lng: number,
  lat: number,
): { x: number; y: number } {
  if (assessGeoreferencing(ctx).mode === 'map') {
    const map = fromWgs84(ctx, lng, lat);
    if (map) {
      const [col, row] = invertAffine(ctx.transform!, map[0], map[1]);
      return { x: col, y: row };
    }
  }
  return { x: lng, y: ctx.height - lat };
}

/**
 * Patch a stored label is attached to, as a pixel window in the source raster.
 *
 * Labels are stored at the point the user clicked, but the training sample is
 * the whole patch and RSAL derives the sample id from that patch. The map draws
 * a query sample at the *centre* of its patch, so recovering the window from the
 * raw clicked point (rather than snapping it to the patch) would move the marker
 * up to half a patch the moment the label is reloaded. Snapping here keeps the
 * saved pin exactly where the suggestion was drawn.
 */
export function patchWindowForLabel(
  ctx: GeoContext,
  grid: { patchSize: number; stride: number },
  geometry: { type: string; coordinates: unknown },
  space: string,
): { x0: number; y0: number; x1: number; y1: number } | null {
  // `map` -> projected CRS; `pixel` -> raster pixels (RSAL stores both).
  const toPixel = (pair: number[]): { x: number; y: number } => {
    if (space === 'pixel') return { x: Number(pair[0]), y: Number(pair[1]) };
    const [col, row] = invertAffine(ctx.transform!, Number(pair[0]), Number(pair[1]));
    return { x: col, y: row };
  };
  if (geometry.type === 'Point') {
    const point = toPixel(geometry.coordinates as number[]);
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
    const cell = pointToCell(ctx, grid, point.x, point.y);
    return cellWindow(ctx, grid, cell.row, cell.col);
  }
  if (geometry.type === 'Polygon') {
    const ring = (geometry.coordinates as number[][][])[0] ?? [];
    const points = ring.map(toPixel).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
    if (!points.length) return null;
    return {
      x0: Math.min(...points.map((p) => p.x)),
      y0: Math.min(...points.map((p) => p.y)),
      x1: Math.max(...points.map((p) => p.x)),
      y1: Math.max(...points.map((p) => p.y)),
    };
  }
  return null;
}

/** Display-space rectangle [w, s, e, n] for a pixel rectangle. */
export function pixelRectToDisplay(
  ctx: GeoContext,
  win: PixelWindow,
): [number, number, number, number] {
  const a = pixelToDisplay(ctx, win.x0, win.y0);
  const b = pixelToDisplay(ctx, win.x1, win.y1);
  return [
    Math.min(a.lng, b.lng),
    Math.min(a.lat, b.lat),
    Math.max(a.lng, b.lng),
    Math.max(a.lat, b.lat),
  ];
}

/**
 * Cell start positions for one axis, mirroring the backend's `make_grid`:
 * regular stride steps from 0, with the last cell clamped to the image edge so
 * the whole extent is covered. Must stay identical to
 * `app/services/raster_service.py::make_grid`.
 */
export function gridAxis(dim: number, patch: number, stride: number): number[] {
  const p = Math.min(patch, dim);
  const starts: number[] = [];
  for (let s = 0; s <= dim - p; s += stride) starts.push(s);
  if (!starts.length) starts.push(0);
  if (starts[starts.length - 1] + p < dim) starts.push(dim - p);
  return starts;
}

/** Exact pixel window of grid cell (row, col). */
export function cellWindow(
  ctx: GeoContext,
  grid: { patchSize: number; stride: number },
  row: number,
  col: number,
): PixelWindow {
  const ys = gridAxis(ctx.height, grid.patchSize, grid.stride);
  const xs = gridAxis(ctx.width, grid.patchSize, grid.stride);
  const clamp = (value: number, max: number) => Math.max(0, Math.min(max, value));
  const y0 = ys[clamp(row, ys.length - 1)];
  const x0 = xs[clamp(col, xs.length - 1)];
  return {
    x0,
    y0,
    x1: Math.min(ctx.width, x0 + Math.min(grid.patchSize, ctx.width)),
    y1: Math.min(ctx.height, y0 + Math.min(grid.patchSize, ctx.height)),
  };
}

/**
 * Grid cell containing a pixel point.
 *
 * Containment is checked before proximity, because a point can sit exactly on a
 * cell boundary: a label stored at a patch origin (which is what a backend
 * `d{dataset}_r{row}_c{col}` id means) must resolve to *that* patch, not to the
 * neighbour it ties with on centre distance.
 */
export function pointToCell(
  ctx: GeoContext,
  grid: { patchSize: number; stride: number },
  x: number,
  y: number,
): { row: number; col: number } {
  const ys = gridAxis(ctx.height, grid.patchSize, grid.stride);
  const xs = gridAxis(ctx.width, grid.patchSize, grid.stride);
  const patchW = Math.min(grid.patchSize, ctx.width);
  const patchH = Math.min(grid.patchSize, ctx.height);

  // Last match wins when cells overlap (the clamped edge cell), which is where
  // the backend places the final patch.
  let col = -1;
  xs.forEach((start, index) => {
    if (x >= start && x < start + patchW) col = index;
  });
  let row = -1;
  ys.forEach((start, index) => {
    if (y >= start && y < start + patchH) row = index;
  });
  if (col >= 0 && row >= 0) return { row, col };

  const nearest = (starts: number[], value: number, patch: number) => {
    let best = 0;
    let bestDistance = Infinity;
    starts.forEach((start, index) => {
      const distance = Math.abs(start + patch / 2 - value);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = index;
      }
    });
    return best;
  };
  return {
    row: row >= 0 ? row : nearest(ys, y, patchH),
    col: col >= 0 ? col : nearest(xs, x, patchW),
  };
}
