import type { RequestHandler } from './$types';
import { toQueryHistory } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalQueryBatch } from '$lib/server/rsal';

/** GET /api/projects/{id}/queries/{batchId} — reopen a batch from any session. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const batch = await rsalGet<RsalQueryBatch>(`/projects/${params.id}/queries/${params.batchId}`);
    return ok(toQueryHistory(batch));
  } catch (error) {
    return fail(error);
  }
};
