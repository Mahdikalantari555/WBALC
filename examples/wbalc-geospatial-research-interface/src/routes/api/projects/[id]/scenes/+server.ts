import type { RequestHandler } from './$types';
import { toScene } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalScene } from '$lib/server/rsal';

/** GET /api/projects/{id}/scenes — registered multi-temporal acquisitions. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const scenes = await rsalGet<RsalScene[]>(`/projects/${params.id}/scenes`);
    return ok(scenes.map(toScene));
  } catch (error) {
    return fail(error);
  }
};
