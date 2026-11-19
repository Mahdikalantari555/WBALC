import { expect, it } from 'vitest';
import { sameNativeGrid, sourcePixel } from './map-inspection';
import { toWgs84 } from './geo';

it('converts geographic UTM clicks to native pixel indices', () => {
  const grid = { crsCode: 'EPSG:32631', transform: [10,0,500000,0,-10,5500000], width: 100, height: 100 };
  const [lon, lat] = toWgs84(grid, 500245, 5499665)!;
  expect(sourcePixel(grid, lon, lat, true)).toEqual({ col: 24, row: 33 });
  expect(sourcePixel(grid, 24.5, 66.5, false)).toEqual({ col: 24, row: 33 });
  expect(sourcePixel(grid, 100, 66.5, false)).toBeNull();
});

it('allows an aligned comparison only when native grids agree', () => {
  const a = { crs: 'EPSG:4326', transform: [1,0,0,0,-1,4], width: 4, height: 4 };
  expect(sameNativeGrid(a, { ...a, crs: 'epsg:4326' })).toBe(true);
  expect(sameNativeGrid(a, { ...a, transform: [1,0,1,0,-1,4] })).toBe(false);
  expect(sameNativeGrid(a, { ...a, crs: null })).toBe(false);
});
