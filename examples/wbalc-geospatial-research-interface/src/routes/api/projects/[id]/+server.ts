import type { RequestHandler } from './$types';
import { toProject } from '$lib/server/adapter';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalGet, type RsalProject } from '$lib/server/rsal';

/** GET /api/projects/{id} — one study project. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const id = parseId(params.id, 'project');
    return ok(toProject(await rsalGet<RsalProject>(`/projects/${id}`)));
  } catch (error) {
    return fail(error);
  }
};
