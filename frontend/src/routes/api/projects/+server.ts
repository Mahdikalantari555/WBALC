import type { RequestHandler } from './$types';
import { toProject } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { ApiError, rsalGet, rsalPost, type RsalProject } from '$lib/server/rsal';

/** GET /api/projects — every study project the engine knows about. */
export const GET: RequestHandler = async () => {
  try {
    const projects = await rsalGet<RsalProject[]>('/projects');
    return ok(projects.map(toProject));
  } catch (error) {
    return fail(error);
  }
};

export const POST: RequestHandler = async ({ request }) => {
  try {
    if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') {
      throw new ApiError('Expected a JSON project.', 415);
    }
    const body = await request.json().catch(() => { throw new ApiError('Invalid JSON.', 400); });
    return ok(toProject(await rsalPost<RsalProject>('/projects', body)), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
