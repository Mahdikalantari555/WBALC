import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('geotiff', () => ({ fromUrl: vi.fn() }));

import { fromUrl } from 'geotiff';
import { inspectRasterPixel, renderRaster, renderWindow } from './raster';

const previewBytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);

describe('server raster preview fallback', () => {
  beforeEach(() => {
    vi.mocked(fromUrl).mockReset().mockRejectedValue(new RangeError('Offset is outside the bounds of the DataView'));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: (name: string) => name.toLowerCase() === 'content-type' ? 'image/png' : null },
      blob: async () => new Blob([previewBytes], { type: 'image/png' }),
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it('routes a GeoTIFF DataView failure to a bounded server PNG without refetching the TIFF', async () => {
    const dataUrl = await renderRaster('/api/projects/4/datasets/8/file', '8', 'true-color', 320, ['blue', 'green', 'red', 'nir']);
    expect(dataUrl).toMatch(/^data:image\/png;base64,/);
    expect(fromUrl).toHaveBeenCalledWith('/api/projects/4/datasets/8/file', { allowFullFile: false, maxRanges: 4 });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith('/api/projects/4/datasets/8/preview?mode=true-color&size=320', {
      headers: { accept: 'image/png' },
    });
  });

  it('forwards exact review windows to the server fallback', async () => {
    await renderWindow('/api/projects/4/scenes/9/file', 'scene:9', { x0: 3, y0: 5, x1: 19, y1: 21 }, 'band:2', 128);
    expect(fetch).toHaveBeenCalledWith(
      '/api/projects/4/scenes/9/preview?mode=band%3A2&size=128&x0=3&y0=5&x1=19&y1=21&upscale=true',
      { headers: { accept: 'image/png' } },
    );
  });

  it('uses GDAL JSON pixel probes when the browser TIFF reader fails', async () => {
    const result = { bands: [{ name: 'nir', value: 12 }, { name: 'red', value: 3 }], difference: true, index: 0.6 };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => result }));
    await expect(inspectRasterPixel('/api/projects/4/scenes/9/file', 'scene:9', 3, 5, 'ndvi', ['blue', 'green', 'red', 'nir']))
      .resolves.toEqual(result);
    expect(fetch).toHaveBeenCalledWith('/api/projects/4/scenes/9/pixel?mode=ndvi&x=3&y=5', {
      headers: { accept: 'application/json' },
    });
  });
});
