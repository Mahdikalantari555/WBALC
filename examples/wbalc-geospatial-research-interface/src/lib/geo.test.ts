import { describe, expect, it } from 'vitest';
import {
  applyAffine,
  approximateAreaKm2,
  assessGeoreferencing,
  cellWindow,
  datasetBounds,
  invertAffine,
  mapToPixel,
  parseUtm,
  ringArea,
  toWgs84,
} from './geo';

const ctx = (crs: string | null, transform: number[] | null = [10, 0, 500000, 0, -10, 4649776]) => ({
  crsCode: crs,
  transform,
  width: 96,
  height: 96,
});

describe('affine', () => {
  it('applies and inverts a rotated affine', () => {
    const rotated = [10, 3, 100, 4, -10, 200];
    const inverse = invertAffine(rotated)!;
    const [x, y] = applyAffine(rotated, 17.5, 42.25);
    const [col, row] = applyAffine(inverse, x, y);
    expect(col).toBeCloseTo(17.5, 9);
    expect(row).toBeCloseTo(42.25, 9);
    const [px, py] = mapToPixel(rotated, x, y)!;
    expect(px).toBeCloseTo(17.5, 9);
    expect(py).toBeCloseTo(42.25, 9);
  });

  it('reports a degenerate affine instead of guessing', () => {
    expect(invertAffine([0, 0, 1, 0, 0, 1])).toBeNull();
  });
});

describe('georeferencing assessment', () => {
  it('accepts WGS84, Web Mercator and WGS84 UTM', () => {
    expect(assessGeoreferencing(ctx('EPSG:4326')).mode).toBe('map');
    expect(assessGeoreferencing(ctx('EPSG:3857')).mode).toBe('map');
    expect(assessGeoreferencing(ctx('EPSG:32631')).mode).toBe('map');
    expect(assessGeoreferencing(ctx('epsg:32756')).mode).toBe('map');
  });

  it('falls back to pixel space with a reason', () => {
    expect(assessGeoreferencing(ctx(null))).toEqual({ mode: 'pixel', reason: 'unsupported-crs' });
    expect(assessGeoreferencing(ctx('EPSG:32631', null))).toEqual({
      mode: 'pixel',
      reason: 'not-georeferenced',
    });
    expect(assessGeoreferencing(ctx('EPSG:3844'))).toEqual({
      mode: 'pixel',
      reason: 'unsupported-crs',
    });
    expect(assessGeoreferencing(ctx('EPSG:32631', [10, 2, 0, 2, -10, 0]))).toEqual({
      mode: 'pixel',
      reason: 'non-axis-aligned',
    });
  });

  it('parses UTM zones and rejects impossible ones', () => {
    expect(parseUtm('EPSG:32631')).toEqual({ zone: 31, south: false });
    expect(parseUtm('EPSG:32756')).toEqual({ zone: 56, south: true });
    expect(parseUtm('EPSG:26915')).toEqual({ zone: 15, south: false });
    expect(parseUtm('EPSG:32661')).toBeNull();
    expect(parseUtm('EPSG:4326')).toBeNull();
  });
});

describe('coordinate conversion', () => {
  it('inverts a UTM easting/northing to lon/lat', () => {
    const [lon, lat] = toWgs84(ctx('EPSG:32631'), 500000, 4649776)!;
    expect(lon).toBeCloseTo(3, 4);
    expect(lat).toBeCloseTo(42, 4);
  });

  it('converts Web Mercator metres', () => {
    const [lon, lat] = toWgs84(ctx('EPSG:3857'), 0, 0)!;
    expect(lon).toBeCloseTo(0, 9);
    expect(lat).toBeCloseTo(0, 9);
  });

  it('returns null rather than a wrong position for an unsupported CRS', () => {
    expect(toWgs84(ctx('EPSG:2154'), 0, 0)).toBeNull();
  });

  it('computes WGS84 bounds only when the grid is usable', () => {
    const bounds = datasetBounds(ctx('EPSG:32631'))!;
    expect(bounds[0]).toBeLessThan(bounds[2]);
    expect(bounds[1]).toBeLessThan(bounds[3]);
    expect(bounds[1]).toBeGreaterThan(41.9);
    expect(datasetBounds(ctx('EPSG:3844'))).toBeNull();
  });
});

describe('prediction cells', () => {
  it('maps a patch cell to its source pixel window, clamped at the edge', () => {
    const grid = { rows: 3, cols: 3, patchSize: 32, stride: 32, region: { x0: 0, y0: 0, x1: 96, y1: 96 } };
    expect(cellWindow(grid, 0, 0, 96, 96)).toEqual({ x0: 0, y0: 0, x1: 32, y1: 32 });
    expect(cellWindow(grid, 2, 2, 96, 96)).toEqual({ x0: 64, y0: 64, x1: 96, y1: 96 });
    // A non-divisible scene keeps the last cell inside the source extent.
    const ragged = { ...grid, region: { x0: 0, y0: 0, x1: 101, y1: 73 } };
    expect(cellWindow(ragged, 2, 3, 101, 73)).toEqual({ x0: 96, y0: 64, x1: 101, y1: 73 });
  });
});

describe('area helpers', () => {
  it('measures a shoelace ring and a rough km² estimate', () => {
    const square: [number, number][] = [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ];
    expect(Math.abs(ringArea(square))).toBe(1);
    const area = approximateAreaKm2(square)!;
    // 1 degree at the equator is ~111.32 km, so ~12 382 km².
    expect(area).toBeGreaterThan(12_000);
    expect(area).toBeLessThan(12_500);
    expect(approximateAreaKm2([[0, 0], [1, 1]])).toBeNull();
  });
});
