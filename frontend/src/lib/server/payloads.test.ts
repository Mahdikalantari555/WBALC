import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sampleResolutionField, trainBody } from './payloads.ts';

test('train defaults keep the historical patch/random behaviour', () => {
  assert.deepEqual(trainBody({}), {
    model_type: 'rf',
    resolution: 'patch',
    evaluation_strategy: 'random',
  });
});

test('train forwards the resolution and evaluation the UI exposes', () => {
  assert.deepEqual(
    trainBody({
      modelType: 'lightgbm',
      resolution: 'pixel',
      evaluationStrategy: 'spatial',
      testSize: 0.3,
      params: { n_estimators: 50 },
    }),
    {
      model_type: 'lightgbm',
      resolution: 'pixel',
      evaluation_strategy: 'spatial',
      test_size: 0.3,
      params: { n_estimators: 50 },
    },
  );
});

test('train ignores out-of-range test sizes instead of failing the request', () => {
  assert.equal(trainBody({ testSize: 1.5 }).test_size, undefined);
  assert.equal(trainBody({ testSize: 0 }).test_size, undefined);
  assert.equal(trainBody({ testSize: 'nope' }).test_size, undefined);
});

test('pixel-mode labels declare their resolution; patch labels keep the default', () => {
  assert.deepEqual(sampleResolutionField({ sampleResolution: 'pixel' }), {
    sample_resolution: 'pixel',
  });
  assert.deepEqual(sampleResolutionField({}), {});
});
