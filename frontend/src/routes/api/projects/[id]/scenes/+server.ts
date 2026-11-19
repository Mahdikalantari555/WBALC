import type { RequestHandler } from './$types';
import { toScene } from '$lib/server/adapter';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalGet, rsalUploadStream, type RsalScene } from '$lib/server/rsal';

/** GET /api/projects/{id}/scenes — registered multi-temporal acquisitions. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const scenes = await rsalGet<RsalScene[]>(`/projects/${parseId(params.id, 'project')}/scenes`);
    return ok(scenes.map(toScene));
  } catch (error) {
    return fail(error);
  }
};

export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    const result = await rsalUploadStream<RsalScene>(`/projects/${id}/scenes`, request);
    return ok(toScene(result), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
