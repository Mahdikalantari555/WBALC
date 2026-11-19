import type { RequestHandler } from './$types';
import { toEvaluationResult } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { ApiError, rsalGet, rsalJson, type RsalEvaluationResult } from '$lib/server/rsal';

/** GET /api/projects/{id}/research/evaluations — held-out scores, oldest first. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const results = await rsalGet<RsalEvaluationResult[]>(`/projects/${params.id}/research/evaluations`);
    return ok(results.map(toEvaluationResult));
  } catch (error) {
    return fail(error);
  }
};

/**
 * POST /api/projects/{id}/research/evaluations — score a protocol's held-out split.
 *
 * The engine refits on the training partition only; the request cannot ask it to
 * score the production model, because that model has seen every labelled sample.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      protocolId?: string;
      modelType?: 'rf' | 'lightgbm';
      resolution?: 'patch' | 'pixel';
    };
    if (!body?.protocolId) throw new ApiError('An evaluation needs a protocol id.', 400);
    const result = await rsalJson<RsalEvaluationResult>(`/projects/${params.id}/research/evaluations`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        protocol_id: Number(body.protocolId),
        model_type: body.modelType ?? 'rf',
        resolution: body.resolution ?? 'patch',
      }),
    });
    return ok(toEvaluationResult(result), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
