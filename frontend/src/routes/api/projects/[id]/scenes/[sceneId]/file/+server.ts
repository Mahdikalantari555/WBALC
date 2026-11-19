import type { RequestHandler } from './$types';
import { fail, parseId } from '$lib/server/http';
import { ApiError, rsalFetch } from '$lib/server/rsal';

export const GET: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    const scene = parseId(params.sceneId, 'scene');
    const range = request.headers.get('range');
    const upstream = await rsalFetch(`/projects/${id}/scenes/${scene}/file`, range ? { headers: { range } } : undefined);
    if (!upstream.ok || !upstream.body) throw new ApiError('Scene raster is unavailable.', upstream.status);
    const headers = new Headers({ 'content-type': 'image/tiff', 'cache-control': 'private, max-age=60' });
    for (const name of ['accept-ranges', 'content-length', 'content-range']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (error) { return fail(error); }
};
