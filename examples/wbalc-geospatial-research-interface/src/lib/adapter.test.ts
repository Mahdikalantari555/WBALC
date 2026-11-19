import { describe, expect, it } from 'vitest';
import { toDataset, toQueryBatch, toQueryHistory, toMetrics, toRun, labelCenter } from './server/adapter';
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
      batch_id: 7,
      strategy: 'diversity',
      method: null,
      seed: null,
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
    expect(view.batchId).toBe('7');
    // A deterministic strategy records no seed rather than a fake one.
    expect(view.seed).toBeNull();
  });

  it('carries the recorded pool of a seeded random batch', () => {
    const view = toQueryBatch({
      batch_id: 12,
      strategy: 'random',
      method: null,
      strategy_version: 'query-v1',
      seed: 99,
      batch_size: 0,
      requested_size: 20,
      model_iteration: null,
      notes: [],
      pool: {
        size: 64,
        hash: 'abc123',
        patch_size: 8,
        stride: 8,
        grid: { rows: 8, cols: 8 },
        grid_cells: 64,
        n_labeled_patches: 0,
        exclude_labeled: true,
        eligibility: 'valid-source-pixels and unlabeled',
      },
      samples: [],
    });
    expect(view.batchId).toBe('12');
    expect(view.seed).toBe(99);
    expect(view.requestedSize).toBe(20);
    expect(view.pool?.hash).toBe('abc123');
    expect(view.pool?.size).toBe(64);
  });

  it('shapes a reopened batch with its decisions and order', () => {
    const entry = toQueryHistory({
      id: 4,
      project_id: 1,
      dataset_id: 2,
      strategy: 'random',
      method: null,
      strategy_version: 'query-v1',
      seed: 5,
      batch_size_requested: 3,
      batch_size_returned: 2,
      pool: {
        size: 62,
        hash: 'h',
        patch_size: 8,
        stride: 8,
        grid: { rows: 8, cols: 8 },
        grid_cells: 64,
        n_labeled_patches: 2,
        exclude_labeled: true,
        eligibility: 'valid-source-pixels and unlabeled',
      },
      parameters: {},
      model_iteration: null,
      training_run_id: null,
      notes: [],
      note: null,
      created_at: '2026-01-02T03:04:05Z',
      decisions: { pending: 1, labeled: 1, rejected: 0, deferred: 0 },
      items: [
        {
          id: 10,
          position: 0,
          sample_id: 'd2_r0_c0',
          dataset_id: 2,
          row: 0,
          col: 0,
          coords: { row: 0, col: 0, x0: 0, y0: 0, x1: 8, y1: 8, center_x: 4, center_y: 4 },
          geo_coords: null,
          score: null,
          uncertainty: null,
          prediction: null,
          confidence: null,
          status: 'labeled',
          decided_class: 'open_water',
          decided_at: '2026-01-02T03:10:00Z',
          decision_note: null,
          label_id: 31,
        },
        {
          id: 11,
          position: 1,
          sample_id: 'd2_r0_c1',
          dataset_id: 2,
          row: 0,
          col: 1,
          coords: { row: 0, col: 1, x0: 8, y0: 0, x1: 16, y1: 8, center_x: 12, center_y: 4 },
          geo_coords: null,
          score: null,
          uncertainty: null,
          prediction: null,
          confidence: null,
          status: 'pending',
          decided_class: null,
          decided_at: null,
          decision_note: null,
          label_id: null,
        },
      ],
    });
    expect(entry.items.map((item) => item.sampleId)).toEqual(['d2_r0_c0', 'd2_r0_c1']);
    expect(entry.items[0].status).toBe('labeled');
    expect(entry.items[0].labelId).toBe('31');
    expect(entry.decisions.labeled).toBe(1);
    expect(entry.poolSize).toBe(62);
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

/* ---------------------------------------- scene results & temporal (Phase 4) */

import {
  toAreaSummary,
  toFusion,
  toSceneAnalysis,
  toTemporalComparison,
  toTemporalSeries,
} from './server/adapter';
import type {
  RsalDateArea,
  RsalFusion,
  RsalSceneAnalysis,
  RsalTemporalComparison,
} from './server/rsal';

const analysis = (overrides: Partial<RsalSceneAnalysis> = {}): RsalSceneAnalysis => ({
  id: 4,
  project_id: 1,
  scene_id: 2,
  training_run_id: 9,
  resolution: 'patch',
  method: 'entropy',
  classes: ['open_water', 'land'],
  grid: { crs: 'EPSG:32631', transform: [10, 0, 500000, 0, -10, 4649776], width: 64, height: 64, sensor: 'Sentinel-1' },
  contract: { verified: true, reason: 'ordered band schema matches' },
  study_area: { applied: false, rule: 'center-in-polygon' },
  artifacts: { hard: { name: 'hard.tif', sha256: 'a'.repeat(64), size_bytes: 10 } },
  areas: {
    available: true,
    per_class: [
      { class_index: 0, class_name: 'open_water', valid_pixels: 700, area_m2: 70000, area_ha: 7, share_of_valid: 0.7 },
      { class_index: 1, class_name: 'land', valid_pixels: 300, area_m2: 30000, area_ha: 3, share_of_valid: 0.3 },
    ],
    valid_pixels: 1000,
    invalid_pixels: 0,
    total_pixels: 1000,
    coverage: 1,
    valid_area_m2: 100000,
    valid_area_ha: 10,
    pixel_area_m2_mean: 100,
    method: { kind: 'projected', supported: true, unit: 'metre', pixel_area_m2: 100 },
    water: { water_classes: ['open_water'], area_m2: 70000, area_ha: 7, share_of_valid: 0.7, valid_area_m2: 100000 },
  },
  lineage: { analysis_digest: 'digest-1', checkpoint_sha256: 'c'.repeat(64) },
  created_at: '2025-04-14T07:41:00Z',
  ...overrides,
});

const dateArea = (overrides: Partial<RsalDateArea> = {}): RsalDateArea => ({
  scene_id: 2,
  analysis_id: 4,
  acquisition_datetime: '2024-01-01T00:00:00Z',
  sensor: 'Sentinel-1',
  valid_area_m2: 100000,
  coverage: 1,
  per_class: analysis().areas.per_class,
  water: null,
  ...overrides,
});

describe('scene analysis view model', () => {
  it('keeps the grid, contract and areas without inventing a method', () => {
    const view = toSceneAnalysis(analysis());
    expect(view.id).toBe('4');
    expect(view.sceneId).toBe('2');
    expect(view.nativeGrid).toBe(true);
    expect(view.crs).toBe('EPSG:32631');
    expect(view.bandContractVerified).toBe(true);
    expect(view.areas.method?.kind).toBe('projected');
    expect(view.analysisDigest).toBe('digest-1');
    expect(view.artifacts.hard.sha256).toHaveLength(64);
  });

  it('reports an unavailable area summary instead of zero-filled confidence', () => {
    const view = toSceneAnalysis(
      analysis({
        areas: {
          available: false,
          reason: 'projected CRS linear unit is not convertible',
          per_class: [],
          valid_pixels: 0,
          invalid_pixels: 0,
          total_pixels: 0,
          coverage: 0,
          valid_area_m2: 0,
          valid_area_ha: 0,
          pixel_area_m2_mean: 0,
          method: { kind: 'projected', supported: false, reason: 'unit not convertible' },
        },
      }),
    );
    expect(view.areas.available).toBe(false);
    expect(view.areas.reason).toContain('not convertible');
    expect(view.areas.perClass).toHaveLength(0);
  });

  it('marks an unverified band contract as such', () => {
    const view = toSceneAnalysis(
      analysis({ contract: { verified: false, reason: 'bands unnamed', override: true } }),
    );
    expect(view.bandContractVerified).toBe(false);
    expect(view.bandContractReason).toBe('bands unnamed');
  });

  it('treats a missing area summary as unavailable, never as zeros with a method', () => {
    const summary = toAreaSummary(null);
    expect(summary.available).toBe(false);
    expect(summary.method).toBeNull();
    expect(summary.reason).toContain('no area summary');
  });
});

describe('temporal series view model', () => {
  it('labels the series native and forwards grid caveats', () => {
    const view = toTemporalSeries({
      project_id: 1,
      classes: ['open_water', 'land'],
      dates: [dateArea(), dateArea({ scene_id: 3, analysis_id: 5, valid_area_m2: 50000 })],
      alignment: { mode: 'native', resampling: 'none', grids_identical: false },
      caveats: ['Scenes 3 are on a different grid from scene 2'],
    });
    expect(view.mode).toBe('native');
    expect(view.gridsIdentical).toBe(false);
    expect(view.caveats).toHaveLength(1);
    expect(view.dates.map((entry) => entry.sceneId)).toEqual(['2', '3']);
  });
});

describe('temporal comparison view model', () => {
  it('reports explicit alignment and the jointly valid denominator', () => {
    const comparison: RsalTemporalComparison = {
      before_scene_id: 2,
      after_scene_id: 3,
      classes: ['open_water', 'land'],
      alignment: { aligned: true, method: 'nearest', reference_scene_id: 2 },
      transitions: {
        classes: ['open_water', 'land'],
        matrix: [
          [10, 5],
          [2, 20],
        ],
        matrix_area_m2: [
          [100, 50],
          [20, 200],
        ],
        joint_valid_pixels: 37,
        joint_valid_area_m2: 370,
        joint_valid_area_ha: 0.037,
        changed_pixels: 7,
        changed_area_m2: 70,
        changed_area_ha: 0.007,
        unchanged_pixels: 30,
        changes: [
          { from: 'open_water', to: 'land', pixels: 5, area_m2: 50, area_ha: 0.005 },
          { from: 'land', to: 'open_water', pixels: 2, area_m2: 20, area_ha: 0.002 },
        ],
        denominator: 'pixels valid in both dates',
      },
      before: dateArea(),
      after: dateArea({ scene_id: 3, analysis_id: 5 }),
      lineage: { comparison_digest: 'd1' },
      caveats: ['Changes are measured after nearest-neighbour alignment'],
    };
    const view = toTemporalComparison(comparison);
    expect(view.aligned).toBe(true);
    expect(view.alignmentMethod).toBe('nearest');
    expect(view.referenceSceneId).toBe('2');
    expect(view.denominator).toBe('pixels valid in both dates');
    expect(view.matrix).toHaveLength(4);
    expect(view.matrix[0]).toEqual({ from: 'open_water', to: 'open_water', pixels: 10, areaM2: 100 });
    expect(view.changedAreaM2).toBe(70);
    expect(view.caveats[0]).toContain('nearest-neighbour');
  });

  it('says no resampling happened when the grids matched', () => {
    const view = toTemporalComparison({
      before_scene_id: 2,
      after_scene_id: 3,
      classes: ['open_water'],
      alignment: { aligned: false, method: 'none', reference_scene_id: 2 },
      transitions: {
        classes: ['open_water'],
        matrix: [[4]],
        matrix_area_m2: [[40]],
        joint_valid_pixels: 4,
        joint_valid_area_m2: 40,
        joint_valid_area_ha: 0.004,
        changed_pixels: 0,
        changed_area_m2: 0,
        changed_area_ha: 0,
        unchanged_pixels: 4,
        changes: [],
        denominator: 'pixels valid in both dates',
      },
      before: dateArea(),
      after: dateArea({ scene_id: 3 }),
      lineage: {},
      caveats: [],
    });
    expect(view.aligned).toBe(false);
    expect(view.transitions).toHaveLength(0);
  });
});

describe('fusion view model', () => {
  const fusion = (overrides: Partial<RsalFusion> = {}): RsalFusion => ({
    id: 7,
    project_id: 1,
    name: 'fusion 2 sources',
    rule: 'weighted_probability',
    weights: { 'Sentinel-1': 0.6, 'Sentinel-2': 0.4 },
    target_grid: { crs: 'EPSG:32631' },
    alignment: { resampling: 'nearest', aligned_sources: [5] },
    missing_policy: 'require_all',
    sources: [
      { analysis_id: 4, scene_id: 2, sensor: 'Sentinel-1', weight: 0.6, grid_aligned: false, analysis_digest: 'd4' },
      { analysis_id: 5, scene_id: 3, sensor: 'Sentinel-2', weight: 0.4, grid_aligned: true, analysis_digest: 'd5' },
    ],
    classes: ['open_water', 'land'],
    areas: analysis().areas,
    agreement: { sources: 2, unanimous_share: 0.75, fused_valid_pixels: 800 },
    artifacts: { hard: { sha256: 'f'.repeat(64) } },
    lineage: { fusion_digest: 'fdigest', fusion_kind: 'late' },
    created_at: '2025-04-14T07:41:00Z',
    ...overrides,
  });

  it('keeps per-source records and flags which one was aligned', () => {
    const view = toFusion(fusion());
    expect(view.aligned).toBe(true);
    expect(view.alignedSources).toEqual(['5']);
    expect(view.sources.map((source) => source.analysisId)).toEqual(['4', '5']);
    expect(view.sources[1].gridAligned).toBe(true);
    expect(view.unanimousShare).toBe(0.75);
  });

  it('reports no alignment when every source shares the target grid', () => {
    const view = toFusion(
      fusion({
        alignment: { resampling: 'none', aligned_sources: [] },
        sources: [
          { analysis_id: 4, scene_id: 2, sensor: 'Sentinel-1', weight: 0.5, grid_aligned: false },
          { analysis_id: 5, scene_id: 3, sensor: 'Sentinel-2', weight: 0.5, grid_aligned: false },
        ],
      }),
    );
    expect(view.aligned).toBe(false);
    expect(view.alignedSources).toEqual([]);
  });

  it('does not invent agreement numbers the engine did not report', () => {
    const view = toFusion(fusion({ agreement: {} }));
    expect(view.unanimousShare).toBeNull();
    expect(view.fusedValidPixels).toBeNull();
  });
});
