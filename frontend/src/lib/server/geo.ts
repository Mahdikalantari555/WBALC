/**
 * Server-side coordinate helpers: dataset CRS <-> WGS84 display space.
 *
 * The maths lives in `@/lib/geo` and is shared verbatim with the browser, so the
 * adapter and the map/thumbnail can never disagree about where a pixel is. This
 * module only adds the RSAL-shaped wrappers.
 */
import type { Bounds, SampleGeometry } from '@/types';
import {
  applyAffine,
  assessGeoreferencing,
  displayToPixel,
  fromWgs84,
  invertAffine,
  patchWindowForLabel,
  pixelRectToDisplay,
  pixelToDisplay,
  pointToCell,
  projectionDef,
  toWgs84,
  type GeoContext,
} from '@/lib/geo';
import type { RsalDataset } from './rsal';

export {
  applyAffine,
  assessGeoreferencing,
  displayToPixel,
  fromWgs84,
  invertAffine,
  patchWindowForLabel,
  pixelRectToDisplay,
  pixelToDisplay,
  projectionDef,
  toWgs84,
};
export type { GeoContext };

/** Adapt RSAL dataset metadata to the shared geo context. */
export function geoContext(dataset: RsalDataset): GeoContext {
  return {
    crsCode: dataset.crs,
    transform: dataset.transform,
    width: dataset.width,
    height: dataset.height,
  };
}

/** A dataset is displayable on the WGS84 map only with a usable CRS + transform. */
export function isGeoreferenced(dataset: RsalDataset): boolean {
  return assessGeoreferencing(geoContext(dataset)).mode === 'map';
}

/** WGS84 [west, south, east, north] for the map, or null for pixel-space scenes. */
export function datasetBounds(dataset: RsalDataset): Bounds | null {
  const ctx = geoContext(dataset);
  if (assessGeoreferencing(ctx).mode !== 'map') return null;
  const t = dataset.transform!;
  const corners = [
    applyAffine(t, 0, 0),
    applyAffine(t, dataset.width, 0),
    applyAffine(t, 0, dataset.height),
    applyAffine(t, dataset.width, dataset.height),
  ]
    .map(([x, y]) => toWgs84(ctx, x, y))
    .filter((p): p is [number, number] => p !== null);
  if (corners.length !== 4) return null;
  const xs = corners.map((c) => c[0]);
  const ys = corners.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** Convert a stored RSAL label geometry into display-space geometry + center. */
export function labelToDisplay(
  dataset: RsalDataset | undefined,
  geometry: { type: string; coordinates: unknown },
  space: string,
): { lat: number; lng: number; geometry: SampleGeometry } | null {
  if (!dataset) return null;
  const ctx = geoContext(dataset);
  const toXY = (pair: number[]): [number, number] | null => {
    let x = Number(pair[0]);
    let y = Number(pair[1]);
    if (space === 'pixel' && dataset.transform) [x, y] = applyAffine(dataset.transform, x, y);
    if (space === 'pixel' || dataset.transform) {
      const wgs = toWgs84(ctx, x, y);
      if (wgs) return wgs;
      // Unknown CRS: fall back to pixel space.
      const [col, row] = space === 'pixel' ? [x, y] : invertAffine(dataset.transform!, x, y);
      return [col, dataset.height - row];
    }
    return [x, dataset.height - y];
  };
  if (geometry.type === 'Point') {
    const xy = toXY(geometry.coordinates as number[]);
    if (!xy) return null;
    return { lng: xy[0], lat: xy[1], geometry: { type: 'Point', coordinates: xy } };
  }
  if (geometry.type === 'Polygon') {
    const rings = geometry.coordinates as number[][][];
    const converted = rings.map((ring) =>
      ring.map((pair) => toXY(pair)).filter((p) => p !== null),
    ) as number[][][];
    const ring = converted[0];
    if (!ring?.length) return null;
    return {
      lng: ring.reduce((a, p) => a + p[0], 0) / ring.length,
      lat: ring.reduce((a, p) => a + p[1], 0) / ring.length,
      geometry: { type: 'Polygon', coordinates: converted },
    };
  }
  return null;
}

/** Recover the pixel window of a stored label, when the geometry defines one. */
export function labelPixelWindow(
  dataset: RsalDataset,
  geometry: { type: string; coordinates: unknown },
  space: string,
  grid: { patchSize: number; stride: number },
): { x0: number; y0: number; x1: number; y1: number } | null {
  return patchWindowForLabel(geoContext(dataset), grid, geometry, space);
}
