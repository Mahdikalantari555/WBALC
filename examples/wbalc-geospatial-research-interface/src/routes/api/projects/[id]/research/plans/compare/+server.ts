import type { RequestHandler } from './$types';
import { toPlanComparison } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { ApiError, rsalJson, type RsalPlanComparison } from '$lib/server/rsal';

/**
 * POST /api/projects/{id}/research/plans/compare — expose shared/differing factors.
 *
 * `paired` is false whenever the results were not scored on the same persisted
 * split; the UI must then show them side by side, not as a controlled comparison.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as { planId?: string; resultIds?: string[] };
    if (!body?.planId) throw new ApiError('A plan comparison needs a plan id.', 400);
    const comparison = await rsalJson<RsalPlanComparison>(
      `/projects/${params.id}/research/plans/compare`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          plan_id: Number(body.planId),
          result_ids: (body.resultIds ?? []).map(Number),
        }),
      },
    );
    return ok(toPlanComparison(comparison));
  } catch (error) {
    return fail(error);
  }
};
