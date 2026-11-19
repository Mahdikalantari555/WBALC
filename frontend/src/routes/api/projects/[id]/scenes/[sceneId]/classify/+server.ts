import type { RequestHandler } from './$types';
import { toSceneAnalysis } from '$lib/server/adapter';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalJson, type RsalSceneClassification } from '$lib/server/rsal';

/**
 * POST /api/projects/{id}/scenes/{sceneId}/classify
 *
 * Classifies the scene on its own grid. The engine refuses (422) when the model's
 * declared bands cannot be proven to match this scene's, so no override is sent
 * implicitly: the caller has to ask for one.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const sceneId = parseId(params.sceneId, 'scene');
    const body = (await request.json().catch(() => ({}))) as {
      method?: string;
      acceptUnverifiedSchema?: boolean;
    };
    const result = await rsalJson<RsalSceneClassification>(
      `/projects/${params.id}/scenes/${sceneId}/classify`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          method: body.method ?? 'entropy',
          accept_unverified_schema: Boolean(body.acceptUnverifiedSchema),
        }),
      },
    );
    return ok(toSceneAnalysis(result.analysis), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
