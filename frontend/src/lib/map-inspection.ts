import proj4 from 'proj4';
import { mapToPixel, normalizeCrs, parseUtm, type GeoContext } from './geo';

export function sourcePixel(grid: GeoContext, x: number, y: number, geographic: boolean) {
  let point: number[] | null = [x, grid.height - y];
  if (geographic) {
    if (!grid.transform) return null;
    const crs = normalizeCrs(grid.crsCode);
    const utm = parseUtm(crs);
    const destination = utm ? `+proj=utm +zone=${utm.zone} ${utm.south ? '+south ' : ''}+datum=WGS84 +units=m` : crs;
    if (!destination) return null;
    try {
      const [mx, my] = proj4('EPSG:4326', destination, [x, y]);
      point = mapToPixel(grid.transform, mx, my);
    } catch { return null; }
  }
  if (!point || !point.every(Number.isFinite)) return null;
  const [col, row] = point.map(Math.floor);
  return col >= 0 && row >= 0 && col < grid.width && row < grid.height ? { col, row } : null;
}

export function sameNativeGrid(a: { crs: string | null; transform: number[] | null; width: number; height: number }, b: typeof a) {
  return !!a.crs && normalizeCrs(a.crs) === normalizeCrs(b.crs) && a.width === b.width && a.height === b.height &&
    a.transform?.length === 6 && b.transform?.length === 6 && a.transform.every((value, index) => Number.isFinite(value) && value === b.transform![index]);
}
