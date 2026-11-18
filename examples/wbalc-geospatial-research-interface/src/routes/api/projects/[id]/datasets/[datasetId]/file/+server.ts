import type { RequestHandler } from './$types';
import { fail } from '$lib/server/http';
import { rsalFetch } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/datasets/{datasetId}/file
 *
 * Streams the original uploaded GeoTIFF bytes. The browser renders bands from
 * this response with geotiff.js; RSAL never reprojects or resamples the source.
 */
export const GET: RequestHandler = async ({ params, request }) => {
  try {
    // Forward Range (when present) so geotiff.js can read windows instead of the
    // whole file; an empty `range:` header would be malformed upstream.
    const range = request.headers.get('range');
    const upstream = await rsalFetch(
      `/projects/${encodeURIComponent(params.id)}/dataset/${encodeURIComponent(params.datasetId)}/file`,
      range ? { headers: { range } } : undefined,
    );
    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text().catch(() => '');
      return fail(new Error(detail || `Dataset file request failed (${upstream.status})`));
    }
    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') ?? 'image/tiff');
    headers.set('cache-control', 'private, max-age=60');
    headers.set('accept-ranges', upstream.headers.get('accept-ranges') ?? 'bytes');
    for (const name of ['content-length', 'content-range']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (error) {
    return fail(error);
  }
};
