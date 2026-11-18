import { describe, expect, it } from 'vitest';
import { toDataset, toQueryBatch, toMetrics, toRun, labelCenter } from './server/adapter';
import type { RsalDataset, RsalLabel, RsalMetrics, RsalQueryResponse } from './server/rsal';

const dataset = (overrides: Partial<RsalDataset> = {}): RsalDataset => ({
  id: 3,
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
  patch_grid: { patch_size: 32, stride: 32, rows: 3, cols: 3, total_patches: 9 },
  ...overrides,
});

describe('dataset view model', () => {
  it('keeps source metadata and derives adapter-only fields', () => {
    const view = toDataset(dataset());
    expect(view.id).toBe('3');
    expect(view.url).toBe('/api/projects/1/datasets/3/file');
    expect(view.georeferenced).toBe(true);
    expect(view.georefReason).toBeNull();
    expect(view.patchGrid?.totalPatches).toBe(9);
    // Bounds are recomputed in WGS84 for the map, not copied from CRS units
    // (the source `bounds` are UTM eastings/northings).
    expect(view.bounds![0]).toBeCloseTo(3, 1);
    expect(view.bounds![1]).toBeCloseTo(41.99, 1);
    expect(view.bounds![2]).toBeCloseTo(3.01, 1);
    expect(view.bounds![3]).toBeCloseTo(42, 1);
  });

  it('marks a raster without a CRS as pixel space', () => {
    const view = toDataset(dataset({ crs: null, transform: null }));
    expect(view.georeferenced).toBe(false);
    expect(view.georefReason).toBe('not-georeferenced');
  });

  it('never coerces a missing patch grid', () => {
    expect(toDataset(dataset({ patch_grid: null })).patchGrid).toBeNull();
  });
});

describe('label projection', () => {
  const lookup = new Map([[3, dataset()]]);
  const label = (space: 'pixel' | 'map', coordinates: number[]): RsalLabel => ({
    id: 1,
    project_id: 1,
    dataset_id: 3,
    sample_id: 'd3_r0_c0',
    sample_type: 'point',
    geometry: { type: 'Point', coordinates },
    coordinate_space: space,
    class_name: 'open_water',
    iteration: 0,
    version: 1,
    created_at: '2025-04-14T07:41:00Z',
  });

  it('projects a pixel-space label through the affine', () => {
    // Pixel (10, 10) -> UTM (500100, 4649676) -> WGS84.
    const center = labelCenter(label('pixel', [10, 10]), lookup)!;
    expect(center[0]).toBeCloseTo(3, 2);
    expect(center[1]).toBeCloseTo(41.999, 2);
  });

  it('projects a map-space label directly', () => {
    const center = labelCenter(label('map', [500100, 4649676]), lookup)!;
    expect(center[0]).toBeCloseTo(3, 2);
    expect(center[1]).toBeCloseTo(41.999, 2);
  });

  it('returns no position when the dataset cannot be projected', () => {
    const unknown = new Map([[3, dataset({ crs: null })]]);
    expect(labelCenter(label('pixel', [1, 1]), unknown)).toBeNull();
    expect(labelCenter(label('pixel', [1, 1]), new Map())).toBeNull();
  });
});

describe('metrics view model', () => {
  const metrics: RsalMetrics = {
    id: 4,
    project_id: 1,
    iteration: 1,
    model_type: 'rf',
    n_samples: 12,
    accuracy: 0.83,
    f1_macro: 0.81,
    f1_weighted: 0.82,
    confusion_matrix: [
      [4, 1],
      [1, 6],
    ],
    per_class: {
      open_water: { precision: 0.8, recall: 0.75, f1: 0.77, support: 5 },
      land: { precision: 0.85, recall: 0.86, f1: 0.85, support: 7 },
    },
    classes: ['open_water', 'land'],
    evaluation: 'random_stratified',
    evaluation_details: null,
    resolution: 'patch',
    evaluation_strategy: 'spatial',
    n_train: 9,
    n_test: 3,
    held_out_groups: 2,
    per_class_iou: { open_water: 0.63 },
    created_at: '2025-04-14T07:41:00Z',
  };

  it('keeps protocol context and per-class order', () => {
    const view = toMetrics(metrics);
    expect(view.perClass.map((row) => row.className)).toEqual(['open_water', 'land']);
    expect(view.perClass[0].iou).toBe(0.63);
    // A class without an IoU stays null instead of becoming 0.
    expect(view.perClass[1].iou).toBeNull();
    expect(view.evaluationStrategy).toBe('spatial');
    expect(view.insufficient).toBe(false);
  });

  it('flags insufficient evaluation rather than inventing a score', () => {
    expect(toMetrics({ ...metrics, evaluation: 'insufficient_train_metrics' }).insufficient).toBe(true);
  });
});

describe('query batch view model', () => {
  it('maps pixel windows and geo centres', () => {
    const response: RsalQueryResponse = {
      strategy: 'diversity',
      method: null,
      batch_size: 1,
      model_iteration: null,
      notes: ['cold start'],
      samples: [
        {
          sample_id: 'd3_r1_c2',
          dataset_id: 3,
          coords: { row: 1, col: 2, x0: 64, y0: 32, x1: 96, y1: 64, center_x: 80, center_y: 48 },
          geo_coords: { bbox: [1, 2, 3, 4], center: [500800, 4649296] },
          prediction: null,
          confidence: null,
          uncertainty: null,
        },
      ],
    };
    const view = toQueryBatch(response);
    const sample = view.samples[0];
    expect(sample.window).toEqual({ x0: 64, y0: 32, x1: 96, y1: 64 });
    expect(sample.geo).toEqual([500800, 4649296]);
    expect(sample.center).toEqual([80, 48]);
    expect(view.notes).toEqual(['cold start']);
  });
});

describe('training run view model', () => {
  const runMetrics: RsalMetrics = {
    id: 33,
    project_id: 1,
    iteration: 4,
    model_type: 'lightgbm',
    n_samples: 40,
    accuracy: 0.9,
    f1_macro: 0.88,
    f1_weighted: 0.89,
    confusion_matrix: [
      [10, 1],
      [1, 12],
    ],
    per_class: {
      open_water: { precision: 0.91, recall: 0.9, f1: 0.9, support: 11 },
      land: { precision: 0.92, recall: 0.92, f1: 0.92, support: 13 },
    },
    classes: ['open_water', 'land'],
    evaluation: 'spatial_holdout',
    evaluation_details: 'held out 2 blocks',
    resolution: 'pixel',
    evaluation_strategy: 'spatial',
    n_train: 30,
    n_test: 10,
    held_out_groups: 2,
    per_class_iou: { open_water: 0.81, land: 0.84 },
    created_at: '2025-04-14T08:00:00Z',
  };

  const response = {
    id: 12,
    project_id: 1,
    iteration: 4,
    model_type: 'lightgbm',
    resolution: 'pixel',
    checkpoint: '/tmp/run12.pkl',
    n_samples: 40,
    metrics: runMetrics,
  };

  it('echoes the resolution and protocol the run was trained with', () => {
    const view = toRun(response as never);
    // A pixel run must never be displayed as a patch run, and vice versa.
    expect(view.resolution).toBe('pixel');
    expect(view.metrics.resolution).toBe('pixel');
    expect(view.metrics.evaluationStrategy).toBe('spatial');
    expect(view.checkpoint).toBe('/tmp/run12.pkl');
  });

  it('carries an insufficient evaluation through unchanged', () => {
    const view = toRun({
      ...response,
      metrics: { ...response.metrics, evaluation: 'insufficient_train_metrics' },
    } as never);
    expect(view.metrics.insufficient).toBe(true);
  });
});
