import type { RequestHandler } from './$types';
import { toDataset } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalDataset } from '$lib/server/rsal';

/** GET /api/projects/{id}/datasets — legacy single-raster datasets of a project. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const datasets = await rsalGet<RsalDataset[]>(`/projects/${params.id}/dataset`);
    return ok(datasets.map(toDataset));
  } catch (error) {
    return fail(error);
  }
};
