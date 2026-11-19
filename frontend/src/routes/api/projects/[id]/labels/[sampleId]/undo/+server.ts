import type { RequestHandler } from './$types';
import { fail, parseId } from '$lib/server/http';
import { rsalPost } from '$lib/server/rsal';

export const POST: RequestHandler = async ({ params }) => {
  try {
    const project = parseId(params.id, 'project');
    const label = parseId(params.sampleId, 'label');
    const data = await rsalPost(`/projects/${project}/labels/${label}/undo`, {});
    return Response.json(data);
  } catch (error) { return fail(error); }
};
