import { describe, expect, it } from 'vitest';
import {
  toComparison,
  toDataset,
  toExperiment,
  toMapField,
  toProject,
  toRun,
  toRunLineage,
} from './server/adapter';
import type { RsalDataset, RsalMapField, RsalProject, RsalRunSummary } from './server/rsal';

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

describe('water taxonomy and derived binary product', () => {
  const project = (
    overrides: Partial<RsalProject> = {},
  ): RsalProject => ({
    id: 4,
    name: 'Estuary',
    description: '',
    classes: ['open_water', 'emergent_vegetation', 'land'],
    status: 'active',
    study_area_geometry: null,
    study_area_crs: null,
    classification_config: {
      internal_classes: ['open_water', 'emergent_vegetation', 'land'],
      binary_output_interpretation: 'water_vs_non_water',
      label_aliases: { emergent_vegetation: ['reed'] },
    },
    taxonomy: {
      version: 'wbalc-water-taxonomy-v1',
      classes: ['open_water', 'emergent_vegetation', 'land'],
      display_names: { open_water: 'Open water' },
      aliases: { emergent_vegetation: ['emergent_vegetation', 'reed'] },
      crosswalk: { reed: 'emergent_vegetation' },
      binary_interpretation: 'water_vs_non_water',
      source: 'default',
    },
    created_at: '2025-04-14T07:41:00Z',
    updated_at: '2025-04-14T07:41:00Z',
    ...overrides,
  });

  it('shapes the water taxonomy with its aliases and version', () => {
    const view = toProject(project());
    expect(view.taxonomy?.version).toBe('wbalc-water-taxonomy-v1');
    expect(view.taxonomy?.classes).toEqual(['open_water', 'emergent_vegetation', 'land']);
    expect(view.taxonomy?.aliases.emergent_vegetation).toContain('reed');
    expect(view.classificationConfig.labelAliases.emergent_vegetation).toEqual(['reed']);
  });

  it('reports a generic project as having no water taxonomy', () => {
    const view = toProject(
      project({
        classes: ['water', 'vegetation'],
        taxonomy: null,
        classification_config: {
          internal_classes: ['water', 'vegetation'],
          binary_output_interpretation: 'water_vs_non_water',
        },
      }),
    );
    expect(view.taxonomy).toBeNull();
    expect(view.classificationConfig.labelAliases).toEqual({});
  });

  it('carries the derived binary mapping and availability', () => {
    const view = toMapField(
      field({
        classes: ['open_water', 'emergent_vegetation', 'land'],
        binary: {
          interpretation: 'water_vs_non_water',
          version: 'binary-water-v1',
          available: true,
          mapping: { open_water: 'water', emergent_vegetation: 'water', land: 'non_water' },
          source_classes: ['open_water', 'emergent_vegetation', 'land'],
          missing_classes: [],
          reason: null,
          taxonomy_version: 'wbalc-water-taxonomy-v1',
          exports: { binary: '/projects/1/download/binary' },
        },
      }),
    );
    expect(view.binary?.available).toBe(true);
    expect(view.binary?.mapping.emergent_vegetation).toBe('water');
    expect(view.binary?.taxonomyVersion).toBe('wbalc-water-taxonomy-v1');
  });

  it('keeps an unavailable binary product visible instead of hiding it', () => {
    const view = toMapField(
      field({
        binary: {
          interpretation: 'water_vs_non_water',
          version: 'binary-water-v1',
          available: false,
          mapping: { open_water: 'water', land: 'non_water' },
          source_classes: ['open_water', 'land'],
          missing_classes: ['emergent_vegetation'],
          reason: 'Binary interpretation needs emergent_vegetation, which this model never learned',
          taxonomy_version: 'wbalc-water-taxonomy-v1',
          exports: {},
        },
      }),
    );
    expect(view.binary?.available).toBe(false);
    expect(view.binary?.missingClasses).toEqual(['emergent_vegetation']);
    expect(view.binary?.reason).toContain('never learned');
  });

  it('reports no binary product for a run that recorded no interpretation', () => {
    expect(toMapField(field({ binary: null })).binary).toBeNull();
  });
});

describe('run lineage and comparison', () => {
  const runRow = (overrides: Partial<RsalRunSummary> = {}): RsalRunSummary => ({
    id: 9,
    project_id: 1,
    iteration: 3,
    model_type: 'rf',
    n_samples: 24,
    accuracy: 0.82,
    f1_macro: 0.79,
    f1_weighted: 0.81,
    confusion_matrix: [[1]],
    per_class: {},
    classes: ['open_water', 'emergent_vegetation', 'land'],
    evaluation: 'random_holdout',
    evaluation_details: null,
    resolution: 'patch',
    evaluation_strategy: 'random',
    n_train: 18,
    n_test: 6,
    held_out_groups: null,
    per_class_iou: {},
    created_at: '2026-02-01T00:00:00Z',
    manifest_hash: 'a'.repeat(64),
    lineage_status: 'complete',
    experiment_id: null,
    checkpoint_sha256: 'b'.repeat(64),
    ...overrides,
  });

  it('reports a complete run with its manifest hash', () => {
    const view = toRun(runRow());
    expect(view.lineageStatus).toBe('complete');
    expect(view.manifestHash).toBe('a'.repeat(64));
    expect(view.metrics.accuracy).toBeCloseTo(0.82);
  });

  it('reports a run with no manifest as legacy rather than guessing', () => {
    const view = toRun(runRow({ manifest_hash: null, lineage_status: 'legacy', checkpoint_sha256: null }));
    expect(view.lineageStatus).toBe('legacy');
    expect(view.manifestHash).toBeNull();
    expect(view.checkpointSha256).toBeNull();
  });

  it('shapes a lineage record, keeping missing fields visible', () => {
    const view = toRunLineage({
      run_id: 9,
      iteration: 3,
      experiment_id: null,
      lineage_status: 'incomplete',
      manifest: {
        hash: 'c'.repeat(64),
        labels: { hash: 'd'.repeat(64) },
        inputs: [{ dataset_id: 1, content_sha256: null }],
        environment: { revision: null, python: '3.11.9' },
        config: { resolution: 'patch' },
      },
      manifest_hash: 'c'.repeat(64),
      missing: ['dataset 1: content hash', 'code revision'],
      artifact: { verified: false, reason: 'no checksum was recorded' },
      notes: ['legacy artifact'],
    });
    expect(view.status).toBe('incomplete');
    expect(view.missing).toContain('code revision');
    expect(view.inputs[0].sha256).toBeNull();
    expect(view.artifact?.verified).toBe(false);
    expect(view.environment?.revision).toBeNull();
  });

  it('shapes a comparison and preserves the not-comparable verdict', () => {
    const view = toComparison({
      experiment_id: 2,
      project_id: 1,
      runs: [
        {
          run_id: 9,
          iteration: 3,
          model_type: 'rf',
          accuracy: 0.8,
          f1_macro: 0.7,
          n_samples: 24,
          evaluation: 'random_holdout',
          lineage_status: 'complete',
          manifest_hash: 'a'.repeat(64),
          label_snapshot_hash: 'e'.repeat(64),
          input_hashes: { '1': 'f'.repeat(64) },
          config: { evaluation_strategy: 'random', resolution: 'patch' },
          environment_revision: 'abc123',
        },
        {
          run_id: 10,
          iteration: 4,
          model_type: 'rf',
          accuracy: 0.7,
          f1_macro: 0.6,
          n_samples: 24,
          evaluation: 'random_holdout',
          lineage_status: 'complete',
          manifest_hash: 'b'.repeat(64),
          label_snapshot_hash: 'g'.repeat(64),
          input_hashes: { '1': 'f'.repeat(64) },
          config: { evaluation_strategy: 'spatial', resolution: 'patch' },
          environment_revision: 'abc123',
        },
      ],
      differences: { label_snapshot_hash: ['e', 'g'], evaluation: ['random', 'spatial'] },
      comparable: false,
      caveats: ['The runs trained on different label versions.'],
    });
    expect(view.comparable).toBe(false);
    expect(view.runs.map((row) => row.runId)).toEqual(['9', '10']);
    expect(Object.keys(view.differences)).toContain('label_snapshot_hash');
    expect(view.caveats).toHaveLength(1);
  });

  it('shapes an experiment with its run membership', () => {
    const view = toExperiment({
      id: 2,
      project_id: 1,
      name: 'Patch vs holdout',
      description: '',
      hypothesis: null,
      config: null,
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
      run_ids: [9, 10],
    });
    expect(view.id).toBe('2');
    expect(view.runIds).toEqual(['9', '10']);
  });
});
