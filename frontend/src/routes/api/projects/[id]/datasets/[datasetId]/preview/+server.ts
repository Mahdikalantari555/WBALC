import type { RequestHandler } from './$types';
import { fail, parseId } from '$lib/server/http';
import { ApiError, rsalFetch } from '$lib/server/rsal';

const PREVIEW_PARAMS = ['mode', 'size', 'x0', 'y0', 'x1', 'y1', 'upscale'] as const;

export const GET: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    const dataset = parseId(params.datasetId, 'dataset');
    const incoming = new URL(request.url).searchParams;
    const query = new URLSearchParams();
    for (const key of PREVIEW_PARAMS) {
      const value = incoming.get(key);
      if (value !== null) query.set(key, value);
    }
    const suffix = query.size ? `?${query}` : '';
    const upstream = await rsalFetch(`/projects/${id}/dataset/${dataset}/preview${suffix}`);
    if (!upstream.ok || !upstream.body) {
      const payload = await upstream.json().catch(() => null) as { detail?: unknown } | null;
      const detail = typeof payload?.detail === 'string' ? payload.detail : `Dataset preview failed (${upstream.status}).`;
      throw new ApiError(detail, upstream.status);
    }
    const headers = new Headers({
      'content-type': upstream.headers.get('content-type') ?? 'image/png',
      'cache-control': upstream.headers.get('cache-control') ?? 'private, max-age=60',
    });
    const length = upstream.headers.get('content-length');
    if (length) headers.set('content-length', length);
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (error) { return fail(error); }
};
