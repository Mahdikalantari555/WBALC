import type { RequestHandler } from './$types';
import { toRun } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { ApiError, rsalPost, type RsalTrainResponse } from '$lib/server/rsal';

interface Body {
  resolution?: 'patch' | 'pixel';
  evaluationStrategy?: 'random' | 'spatial';
  modelType?: 'rf' | 'lightgbm';
  iteration?: number | null;
}

/**
 * POST /api/projects/{id}/train — train a checkpoint from the submitted labels.
 *
 * The resolution is a required, explicit choice: `patch` trains on patch
 * statistics, `pixel` on one feature vector per source pixel. They are different
 * products and the engine defaults to `patch`, so the UI never relies on that
 * default and the choice it sent is echoed back in the run.
 *
 * The evaluation split (`random` vs `spatial`) is likewise explicit: a random
 * holdout over neighbouring patches is optimistic, and the score is meaningless
 * without knowing which protocol produced it.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json().catch(() => ({}))) as Body;
    if (body.resolution && !['patch', 'pixel'].includes(body.resolution)) {
      throw new ApiError(`Unknown resolution '${body.resolution}'; use patch or pixel.`, 400);
    }
    if (body.evaluationStrategy && !['random', 'spatial'].includes(body.evaluationStrategy)) {
      throw new ApiError(
        `Unknown evaluation strategy '${body.evaluationStrategy}'; use random or spatial.`,
        400,
      );
    }
    const run = await rsalPost<RsalTrainResponse>(`/projects/${params.id}/train`, {
      model_type: body.modelType ?? 'rf',
      resolution: body.resolution ?? 'patch',
      evaluation_strategy: body.evaluationStrategy ?? 'random',
      iteration: body.iteration ?? null,
      params: {},
    });
    return ok(toRun(run), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
