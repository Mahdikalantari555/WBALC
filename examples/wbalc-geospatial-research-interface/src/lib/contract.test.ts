import { describe, expect, it } from 'vitest';
import { toDataset, toMapField } from './server/adapter';
import type { RsalDataset, RsalMapField } from './server/rsal';

/**
 * Phase 0 (harden-pixel-classification-contract) contract tests.
 *
 * These cover only what the adapter may honestly report: the band identity a
 * dataset declares, and whether the engine proved the reference raster carries
 * the model's bands. Nothing here invents a schema the engine did not record.
 */

const dataset = (overrides: Partial<RsalDataset> = {}): RsalDataset => ({
  id: 5,
  project_id: 1,
  filename: 'scene.tif',
  crs: 'EPSG:32631',
  transform: [10, 0, 500000, 0, -10, 4649776],
  width: 96,
  height: 96,
  bands: 4,
  dtype: 'uint16',
  nodata: null,
  bounds: [500000, 4648816, 500960, 4649776],
  created_at: '2025-04-14T07:41:00Z',
  size_bytes: 1024,
  band_schema: {
    version: 'band-schema-v1',
    band_count: 4,
    band_names: ['blue', 'green', 'red', 'nir'],
    sensor: 'sentinel-2',
    declared: true,
    source: 'request',
    digest: 'a'.repeat(32),
  },
  patch_grid: { patch_size: 32, stride: 32, rows: 3, cols: 3, total_patches: 9 },
  ...overrides,
});

const field = (overrides: Partial<RsalMapField> = {}): RsalMapField => ({
  layer: 'hard',
  method: null,
  project_id: 1,
  dataset_id: 5,
  model_iteration: 2,
  training_run_id: 7,
  classes: ['water', 'vegetation'],
  resolution: 'patch',
  grid: { rows: 2, cols: 2, patch_size: 32, stride: 32, region: { x0: 0, y0: 0, x1: 64, y1: 64 } },
  values: [[0, 1], [1, 0]],
  valid: [[true, true], [true, true]],
  min: 0,
  max: 1,
  stale: false,
  band_schema_verified: true,
  band_schema_reason: 'ordered band schema matches',
  study_area_applied: true,
  study_area_note: 'study area applied',
  exports: {},
  ...overrides,
});

describe('dataset band identity', () => {
  it('reports the ordered band names a raster declares', () => {
    const view = toDataset(dataset());
    expect(view.bandNames).toEqual(['blue', 'green', 'red', 'nir']);
    expect(view.bandSchemaDeclared).toBe(true);
    expect(view.sensor).toBe('sentinel-2');
  });

  it('never guesses a schema for unnamed bands', () => {
    const view = toDataset(
      dataset({
        band_schema: {
          version: 'band-schema-v1',
          band_count: 4,
          band_names: null,
          sensor: null,
          declared: false,
          source: 'raster-metadata',
          digest: 'b'.repeat(32),
        },
      }),
    );
    expect(view.bandNames).toBeNull();
    expect(view.bandSchemaDeclared).toBe(false);
    expect(view.sensor).toBeNull();
  });

  it('treats a missing band_schema (older engine) as undeclared', () => {
    const view = toDataset(dataset({ band_schema: undefined }));
    expect(view.bandNames).toBeNull();
    expect(view.bandSchemaDeclared).toBe(false);
  });

  it('keeps a partially named stack undeclared rather than half-true', () => {
    const view = toDataset(
      dataset({
        band_schema: {
          version: 'band-schema-v1',
          band_count: 4,
          band_names: null,
          sensor: null,
          declared: false,
          source: 'raster-metadata',
          digest: null,
        },
      }),
    );
    expect(view.bandSchemaDeclared).toBe(false);
  });
});

describe('map field provenance', () => {
  it('carries the schema verdict and the study-area decision', () => {
    const view = toMapField(field());
    expect(view.bandSchemaVerified).toBe(true);
    expect(view.studyAreaApplied).toBe(true);
    expect(view.studyAreaNote).toBe('study area applied');
  });

  it('reports an unverified schema instead of implying a match', () => {
    const view = toMapField(
      field({ band_schema_verified: false, band_schema_reason: 'ordered band names differ' }),
    );
    expect(view.bandSchemaVerified).toBe(false);
    expect(view.bandSchemaReason).toBe('ordered band names differ');
  });

  it('does not claim a mask or a verified schema when the engine was silent', () => {
    const view = toMapField(
      field({
        band_schema_verified: undefined,
        band_schema_reason: undefined,
        study_area_applied: undefined,
        study_area_note: undefined,
      }),
    );
    expect(view.bandSchemaVerified).toBe(false);
    expect(view.studyAreaApplied).toBe(false);
    expect(view.studyAreaNote).toBeNull();
  });
});
