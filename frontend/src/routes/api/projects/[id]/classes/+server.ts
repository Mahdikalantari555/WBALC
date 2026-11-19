import type { RequestHandler } from './$types';
import { toProject } from '$lib/server/adapter';
import { fail, ok, parseId } from '$lib/server/http';
import { ApiError, rsalPost, type RsalProject } from '$lib/server/rsal';

export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') throw new ApiError('Expected JSON.', 415);
    const payload = await request.json().catch(() => { throw new ApiError('Invalid JSON.', 400); });
    return ok(toProject(await rsalPost<RsalProject>(`/projects/${id}/classes`, payload)));
  } catch (error) { return fail(error); }
};
