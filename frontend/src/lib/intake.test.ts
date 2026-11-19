import { describe, expect, it } from 'vitest';
import { bandSchemaKey, folderDate, inferBand, planFolder, planManual, validNames } from './intake';
import { channelsFor } from './raster';

function virtual(path: string, content = '') {
  const file = new File([content], path.split('/').at(-1)!);
  Object.defineProperty(file, 'webkitRelativePath', { value: path });
  return file;
}

describe('band confirmation scope', () => {
  it('shares one confirmation across dates only for the same sensor and ordered mapping', () => {
    const first = bandSchemaKey('Sentinel-2', ['blue', 'green', 'red', 'SCL']);
    expect(bandSchemaKey('Sentinel-2', ['BLUE', 'green', 'red', 'scl'])).toBe(first);
    expect(bandSchemaKey('Sentinel-1', ['blue', 'green', 'red', 'scl'])).not.toBe(first);
    expect(bandSchemaKey('Sentinel-2', ['green', 'blue', 'red', 'scl'])).not.toBe(first);
  });
});

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
  it('recognizes Sentinel band aliases, prefixed acquisition folders, metadata, and excludes merged products', async () => {
    expect(folderDate('sentinel1_20250311_desc')).toBe('2025-03-11');
    expect(folderDate('sentinel_20250313')).toBe('2025-03-13');
    expect(inferBand('nir08.tif')).toBe('nir08');
    expect(inferBand('B11_20m.tif')).toBe('swir16');
    expect(inferBand('B12.tif')).toBe('swir22');
    expect(inferBand('SCL_20m.tif')).toBe('scl');

    const metadata = JSON.stringify({
      item_id: 'S1A_IW_GRDH_20250311', datetime: '2025-03-11', platform: 'sentinel-1a',
      constellation: 'Sentinel-1', sensor: 'SAR-C', processing_level: 'L1 GRD',
      polarizations: 'vv / vh', instrument_mode: 'IW', orbit_state: 'descending', relative_orbit: 79,
      properties: { datetime: '2025-03-11T04:02:28.491370+01:00', 'sat:relative_orbit': 79,
        'sat:orbit_state': 'descending', 'sar:instrument_mode': 'IW', 'sar:polarizations': ['VV', 'VH'],
        'sar:product_type': 'GRD' },
      METADATA: { PRODUCT_METADATA: { ACQUISITION_DATE: '2025-03-11', PLATFORM: 'sentinel-1a', PROCESSING_LEVEL: 'GRD' } },
    });
    const [job] = await planFolder([
      virtual('s1_scenes/sentinel1_20250311_desc/merged.tif'),
      virtual('s1_scenes/sentinel1_20250311_desc/vh.tif'),
      virtual('s1_scenes/sentinel1_20250311_desc/vv.tif'),
      virtual('s1_scenes/sentinel1_20250311_desc/MTL.json', metadata),
    ]);
    expect(job.files.map(file => file.name)).toEqual(['vv.tif', 'vh.tif']);
    expect(job.names).toEqual(['vv', 'vh']);
    expect(job.ignoredMerged).toBe(1);
    expect(job.date).toBe('2025-03-11T03:02:28.491370Z');
    expect(job.platform).toBe('Sentinel-1A');
    expect(job.sensor).toBe('Sentinel-1');
    expect(job.metadata?.polarization).toEqual(['VH', 'VV']);
    expect(job.metadata?.acquisitionMode).toBe('IW');
    expect(job.metadata?.orbitDirection).toBe('descending');
    expect(job.metadata?.relativeOrbit).toBe(79);
    expect(job.metadata?.productType).toBe('GRD');
    expect(job.metadata?.productLevel).toBe('L1 GRD');
  });

  it('loads metadata selected with manual band files', async () => {
    const [job] = await planManual([
      virtual('blue.tif'), virtual('green.tif'), virtual('red.tif'), virtual('nir08.tif'),
      virtual('swir16.tif'), virtual('swir22.tif'), virtual('scl.tif'),
      virtual('metadata.json', '{"PRODUCT_METADATA":{"ACQUISITION_DATE":"2025-06-01","PLATFORM":"Sentinel-2A","PROCESSING_LEVEL":"L2A","NATIVE_BAND_RESOLUTIONS":{"B02":10}}}'),
    ]);
    expect(job.names).toEqual(['blue', 'green', 'red', 'nir08', 'swir16', 'swir22', 'scl']);
    expect(job.date).toBe('2025-06-01T00:00:00Z');
    expect(job.sensor).toBe('Sentinel-2');
    expect(job.platform).toBe('Sentinel-2A');
    expect(job.metadata?.productLevel).toBe('L2A');
    expect(job.metadata?.nativeBandResolutions).toEqual({ B02: 10 });
  });

  it('prevents ambiguous dates and mixed sensors, while leaving undated scenes editable', async () => {
    expect(folderDate('2025-02-29')).toBe('');
    expect(inferBand('some-unknown.tif')).toBe('');
    expect(validNames(['VV','vv'])).toBe(false);
    const [undated] = await planFolder([virtual('stack/vv.tif')]);
    expect(undated.date).toBe('');
    expect(undated.error).toBeUndefined();
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
