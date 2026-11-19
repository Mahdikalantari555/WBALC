import type { RequestHandler } from './$types';
import { toScientificStatus } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalScientificStatus } from '$lib/server/rsal';

/** GET /api/projects/{id}/research/status — software vs scientific validity. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const status = await rsalGet<RsalScientificStatus>(`/projects/${params.id}/research/status`);
    return ok(toScientificStatus(status));
  } catch (error) {
    return fail(error);
  }
};
