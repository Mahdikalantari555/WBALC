import type { RequestHandler } from './$types';
import { toRun } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalRunSummary } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/runs — recorded training runs, newest first.
 *
 * `/runs` is used rather than `metrics/history` because each entry also carries
 * the run's lineage pointer (manifest hash, completeness, experiment), which the
 * evaluation view needs in order to say whether two scores are comparable.
 */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const history = await rsalGet<RsalRunSummary[]>(`/projects/${params.id}/runs`);
    return ok(history.map(toRun).reverse());
  } catch (error) {
    return fail(error);
  }
};
