import type { RequestHandler } from './$types';
import { toDataset } from '$lib/server/adapter';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalGet, rsalUploadStream, type RsalDataset } from '$lib/server/rsal';

/** GET /api/projects/{id}/datasets — legacy single-raster datasets of a project. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const datasets = await rsalGet<RsalDataset[]>(`/projects/${parseId(params.id, 'project')}/dataset`);
    return ok(datasets.map(toDataset));
  } catch (error) {
    return fail(error);
  }
};

export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    const result = await rsalUploadStream<RsalDataset>(`/projects/${id}/upload`, request);
    return ok(toDataset(result), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
