import type { RequestHandler } from './$types';
import { toProject } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalProject } from '$lib/server/rsal';

/** GET /api/projects — every study project the engine knows about. */
export const GET: RequestHandler = async () => {
  try {
    const projects = await rsalGet<RsalProject[]>('/projects');
    return ok(projects.map(toProject));
  } catch (error) {
    return fail(error);
  }
};
