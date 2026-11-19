import { describe, expect, it } from 'vitest';
import { folderDate, inferBand, planFolder, validNames } from './intake';
import { channelsFor } from './raster';

function virtual(path: string, content = '') {
  const file = new File([content], path.split('/').at(-1)!);
  Object.defineProperty(file, 'webkitRelativePath', { value: path });
  return file;
}

describe('folder intake', () => {
  it('orders named optical/radar bands independently of picker order and retains the acquisition time', async () => {
    const jobs = await planFolder([
      virtual('stack/20251009/vh.tiff'), virtual('stack/2025-10-01/B04.tif'), virtual('stack/20251009/vv.tiff'),
      virtual('stack/2025-10-01/green.tif'), virtual('stack/2025-10-01/blue.tif'),
      virtual('stack/20251009/metadata.json', '{"properties":{"datetime":"2025-10-09T16:05:00Z","platform":"Sentinel-1A"}}'),
    ]);
    expect(jobs.map(j => [j.sensor, j.names])).toEqual([['Sentinel-2', ['blue','green','red']], ['Sentinel-1', ['vv','vh']]]);
    expect(jobs[1].date).toBe('2025-10-09T16:05:00.000Z');
  });
  it('prevents ambiguous dates and mixed sensors', async () => {
    expect(folderDate('2025-02-29')).toBe('');
    expect(inferBand('some-unknown.tif')).toBe('');
    expect(validNames(['VV','vv'])).toBe(false);
    const [mixed, conflicting] = await planFolder([
      virtual('stack/20250101/vv.tif'), virtual('stack/20250101/red.tif'),
      virtual('stack/20250102/vv.tif'), virtual('stack/20250102/metadata.json', '{"date":"2025-01-03"}'),
    ]);
    expect(mixed.error).toBe('mixedSensor');
    expect(conflicting.error).toBe('dateConflict');
  });
});

describe('raster views', () => {
  it('uses band identity, not RGB position; radar has no NDVI', () => {
    expect(channelsFor('true-color', 4, ['blue', 'green', 'red', 'nir']).channels).toEqual([2, 1, 0]);
    expect(channelsFor('ndvi', 2, ['vv', 'vh']).difference).toBe(false);
    expect(channelsFor('nd:1:0', 2, ['vv', 'vh'])).toEqual({channels:[1, 0], red:0, nir:1, difference:true});
  });
});
