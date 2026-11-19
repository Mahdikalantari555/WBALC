import type { RequestHandler } from './$types';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalUploadStream } from '$lib/server/rsal';

export const POST: RequestHandler = async ({ params, request }) => {
  try {
    return ok(await rsalUploadStream(`/projects/${parseId(params.id, 'project')}/raster-stack`, request), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
