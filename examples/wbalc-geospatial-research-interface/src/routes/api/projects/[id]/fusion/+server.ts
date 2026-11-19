import type { RequestHandler } from './$types';
import { toFusion } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, rsalJson, type RsalFusion } from '$lib/server/rsal';

/** GET /api/projects/{id}/fusion — recorded late-fusion runs, oldest first. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const fusions = await rsalGet<RsalFusion[]>(`/projects/${params.id}/fusion`);
    return ok(fusions.map(toFusion));
  } catch (error) {
    return fail(error);
  }
};

/**
 * POST /api/projects/{id}/fusion — late fusion of derived per-sensor products.
 *
 * `early_fusion` / `raw_band_fusion` are deliberately not offered: the engine
 * rejects them, so the adapter does not pretend they exist.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      name?: string;
      rule?: string;
      targetSceneId?: string;
      analysisIds?: string[];
      weights?: Record<string, number>;
      missingPolicy?: 'require_all' | 'renormalise';
      priority?: string[];
    };
    if (!body?.targetSceneId) throw new Error('A fusion needs a target scene (its grid is used).');
    if (!body.analysisIds?.length || body.analysisIds.length < 2) {
      throw new Error('A fusion needs at least two scene analyses.');
    }
    const fusion = await rsalJson<RsalFusion>(`/projects/${params.id}/fusion`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name: body.name ?? '',
        rule: body.rule ?? 'weighted_probability',
        target_scene_id: Number(body.targetSceneId),
        analysis_ids: body.analysisIds.map(Number),
        weights: body.weights ?? {},
        missing_policy: body.missingPolicy ?? 'require_all',
        priority: (body.priority ?? []).map(Number),
      }),
    });
    return ok(toFusion(fusion), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
