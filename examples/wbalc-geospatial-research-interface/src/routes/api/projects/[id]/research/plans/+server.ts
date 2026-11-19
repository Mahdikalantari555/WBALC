import type { RequestHandler } from './$types';
import { toResearchPlan } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { ApiError, rsalGet, rsalJson, type RsalResearchPlan } from '$lib/server/rsal';

/** GET /api/projects/{id}/research/plans — declared comparisons. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const plans = await rsalGet<RsalResearchPlan[]>(`/projects/${params.id}/research/plans`);
    return ok(plans.map(toResearchPlan));
  } catch (error) {
    return fail(error);
  }
};

/** POST /api/projects/{id}/research/plans — declare factors before running them. */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      name?: string;
      hypothesis?: string | null;
      protocolId?: string | null;
      comparisonMetric?: string;
      factors?: Record<string, unknown>[];
      repetitions?: number;
    };
    if (!body?.name?.trim()) throw new ApiError('A research plan needs a name.', 400);
    const plan = await rsalJson<RsalResearchPlan>(`/projects/${params.id}/research/plans`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name: body.name.trim(),
        hypothesis: body.hypothesis ?? null,
        protocol_id: body.protocolId ? Number(body.protocolId) : null,
        comparison_metric: body.comparisonMetric ?? 'f1_macro',
        factors: body.factors ?? [],
        repetitions: body.repetitions ?? 1,
      }),
    });
    return ok(toResearchPlan(plan), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
