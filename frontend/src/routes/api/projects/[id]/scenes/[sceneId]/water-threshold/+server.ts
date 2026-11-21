import type { RequestHandler } from './$types';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalJson } from '$lib/server/rsal';

export const GET: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    const scene = parseId(params.sceneId, 'scene');
    const incoming = new URL(request.url).searchParams;
    const query = new URLSearchParams();
    const index = incoming.get('index');
    if (index !== null) query.set('index', index);
    const suffix = query.toString() ? `?${query}` : '';
    const result = await rsalJson<Record<string, unknown>>(
      `/projects/${id}/scenes/${scene}/water-threshold${suffix}`,
    );
    return ok(result);
  } catch (error) { return fail(error); }
};
