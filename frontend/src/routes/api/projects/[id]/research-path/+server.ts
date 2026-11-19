import type { RequestHandler } from './$types';
import { fail, parseId } from '$lib/server/http';
import { ApiError, rsalFetch } from '$lib/server/rsal';

export const GET: RequestHandler = async ({ params, url }) => {
  try {
    const id = parseId(params.id, 'project');
    const format = url.searchParams.get('format') ?? 'json';
    if (format !== 'json' && format !== 'csv') throw new ApiError('Choose JSON or CSV.', 400);
    const upstream = await rsalFetch(`/projects/${id}/research-path?format=${format}`);
    if (!upstream.ok) {
      const body = await upstream.json().catch(() => null);
      throw new ApiError(typeof body?.detail === 'string' ? body.detail : 'Research export failed.', upstream.status);
    }
    return new Response(upstream.body, {
      headers: {
        'content-type': upstream.headers.get('content-type') ?? 'application/octet-stream',
        'content-disposition': `attachment; filename="wbalc-${id}-research-path.${format}"`,
        'cache-control': 'no-store',
      },
    });
  } catch (error) {
    return fail(error);
  }
};
