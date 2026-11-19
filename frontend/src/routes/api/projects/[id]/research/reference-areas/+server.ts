import type { RequestHandler } from './$types';
import { toReferenceArea } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { ApiError, rsalGet, rsalJson, type RsalReferenceArea } from '$lib/server/rsal';

/** GET /api/projects/{id}/research/reference-areas — operator-supplied truth. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const areas = await rsalGet<RsalReferenceArea[]>(`/projects/${params.id}/research/reference-areas`);
    return ok(areas.map(toReferenceArea));
  } catch (error) {
    return fail(error);
  }
};

/**
 * POST /api/projects/{id}/research/reference-areas — record an independent area.
 *
 * The source and measurement method are mandatory: an area without provenance is
 * not a reference, and the engine will not invent one.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      sceneId?: string | null;
      label?: string;
      waterAreaM2?: number;
      source?: string;
      method?: string;
      uncertaintyM2?: number | null;
    };
    if (typeof body?.waterAreaM2 !== 'number' || body.waterAreaM2 < 0) {
      throw new ApiError('A reference area needs a non-negative water area in m².', 400);
    }
    if (!body.source?.trim() || !body.method?.trim()) {
      throw new ApiError('A reference area needs both a source and a measurement method.', 400);
    }
    const area = await rsalJson<RsalReferenceArea>(`/projects/${params.id}/research/reference-areas`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        scene_id: body.sceneId ? Number(body.sceneId) : null,
        label: body.label ?? '',
        water_area_m2: body.waterAreaM2,
        source: body.source.trim(),
        method: body.method.trim(),
        uncertainty_m2: body.uncertaintyM2 ?? null,
      }),
    });
    return ok(toReferenceArea(area), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
