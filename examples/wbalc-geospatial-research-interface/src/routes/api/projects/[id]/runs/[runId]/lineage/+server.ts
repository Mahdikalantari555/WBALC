import type { RequestHandler } from './$types';
import { toRunLineage } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalRunLineage } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/runs/{runId}/lineage — what this run was made of.
 *
 * The engine reports `legacy` when a run predates manifests and names the fields
 * it cannot prove; this route never fills those in.
 */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const lineage = await rsalGet<RsalRunLineage>(`/projects/${params.id}/runs/${params.runId}/lineage`);
    return ok(toRunLineage(lineage));
  } catch (error) {
    return fail(error);
  }
};
