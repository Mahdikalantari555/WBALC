import type { RequestHandler } from './$types';
import { fail } from '$lib/server/http';
import { ApiError, rsalFetch } from '$lib/server/rsal';

const TYPES = new Set([
  'hard',
  'probability',
  'uncertainty',
  // Derived from the three-class product, served as their own files.
  'binary',
  'binary_probability',
]);

/**
 * GET /api/projects/{id}/exports?type=hard|probability|uncertainty&dataset=…&accept_unverified_schema=true
 *
 * Streams an engine-produced GeoTIFF through the adapter. The map's "Export
 * view" uses this for the classification product, so the file the user saves is
 * the file the engine wrote on the source grid.
 */
export const GET: RequestHandler = async ({ params, url }) => {
  try {
    const type = url.searchParams.get('type') ?? 'hard';
    if (!TYPES.has(type)) throw new ApiError(`Unknown export type '${type}'.`, 400);
    const dataset = url.searchParams.get('dataset');
    const query = new URLSearchParams();
    if (dataset && /^\d+$/.test(dataset)) query.set('dataset_id', dataset);
    if (type === 'uncertainty') query.set('method', url.searchParams.get('method') ?? 'entropy');
    if (url.searchParams.get('accept_unverified_schema') === 'true') {
      query.set('accept_unverified_schema', 'true');
    }
    const upstream = await rsalFetch(
      `/projects/${params.id}/download/${type}?${query.toString()}`,
    );
    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text().catch(() => '');
      throw new ApiError(detail || `Export request failed (${upstream.status})`, upstream.status);
    }
    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') ?? 'image/tiff');
    headers.set(
      'content-disposition',
      upstream.headers.get('content-disposition') ??
        `attachment; filename="wbalc-${type}-${params.id}.tif"`,
    );
    headers.set('cache-control', 'no-store');
    return new Response(upstream.body, { status: 200, headers });
  } catch (error) {
    return fail(error);
  }
};
