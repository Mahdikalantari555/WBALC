import type { RequestHandler } from './$types';
import { toSceneAnalysis } from '$lib/server/adapter';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalGet, type RsalSceneAnalysis } from '$lib/server/rsal';

/** GET /api/projects/{id}/scenes/{sceneId}/analyses — every classification, oldest first. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const sceneId = parseId(params.sceneId, 'scene');
    const analyses = await rsalGet<RsalSceneAnalysis[]>(
      `/projects/${params.id}/scenes/${sceneId}/analyses`,
    );
    return ok(analyses.map(toSceneAnalysis));
  } catch (error) {
    return fail(error);
  }
};
