import type { RequestHandler } from './$types';
import { toComparison } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalComparison } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/compare?runs=1,2 — compare runs and say where they differ.
 *
 * `comparable` is false whenever the engine found differing inputs, label
 * snapshots, configuration or evaluation protocol; the UI must not present the
 * scores as a controlled comparison in that case.
 */
export const GET: RequestHandler = async ({ params, url }) => {
  try {
    const runs = url.searchParams.get('runs');
    const query = runs ? `?run_ids=${encodeURIComponent(runs)}` : '';
    const comparison = await rsalGet<RsalComparison>(`/projects/${params.id}/compare${query}`);
    return ok(toComparison(comparison));
  } catch (error) {
    return fail(error);
  }
};
