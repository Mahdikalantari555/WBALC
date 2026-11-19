import type { RequestHandler } from './$types';
import { toTemporalComparison } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalJson, type RsalTemporalComparison } from '$lib/server/rsal';

/**
 * POST /api/projects/{id}/temporal/compare — class transitions between two dates.
 *
 * The engine fails closed (409 `grid_mismatch`) when the two analyses are on
 * different grids; `referenceSceneId` is passed through only when the user has
 * explicitly asked for nearest-neighbour alignment onto that scene's grid.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      beforeSceneId?: string;
      afterSceneId?: string;
      referenceSceneId?: string | null;
    };
    if (!body?.beforeSceneId || !body?.afterSceneId) {
      throw new Error('A temporal comparison needs two scenes.');
    }
    const payload: Record<string, unknown> = {
      before_scene_id: Number(body.beforeSceneId),
      after_scene_id: Number(body.afterSceneId),
    };
    if (body.referenceSceneId) {
      payload.reference_scene_id = Number(body.referenceSceneId);
      payload.resampling = 'nearest';
    }
    const comparison = await rsalJson<RsalTemporalComparison>(
      `/projects/${params.id}/temporal/compare`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      },
    );
    return ok(toTemporalComparison(comparison));
  } catch (error) {
    return fail(error);
  }
};
