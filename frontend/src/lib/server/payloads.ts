/**
 * Pure workspace → RSAL request payload builders.
 *
 * Kept free of `next/*` imports so the adapter contract can be unit-tested
 * (`npm test`) without booting the framework.
 */

/** Workspace train form -> RSAL `/train` payload. */
export function trainBody(body: Record<string, unknown>): Record<string, unknown> {
  const testSize = Number(body.testSize);
  return {
    model_type: body.modelType === 'lightgbm' ? 'lightgbm' : 'rf',
    resolution: body.resolution === 'pixel' ? 'pixel' : 'patch',
    evaluation_strategy: body.evaluationStrategy === 'spatial' ? 'spatial' : 'random',
    ...(Number.isFinite(testSize) && testSize > 0 && testSize < 1
      ? { test_size: testSize }
      : {}),
    ...(body.params && typeof body.params === 'object' ? { params: body.params } : {}),
  };
}

/**
 * `sample_resolution` for a label request, when the workspace knows it.
 *
 * Pixel-mode point labels must declare their resolution: otherwise two points in
 * one patch derive the same sample id and the second silently replaces the first.
 */
export function sampleResolutionField(input: {
  sampleResolution?: 'pixel' | 'patch';
}): Record<string, unknown> {
  return input.sampleResolution ? { sample_resolution: input.sampleResolution } : {};
}
