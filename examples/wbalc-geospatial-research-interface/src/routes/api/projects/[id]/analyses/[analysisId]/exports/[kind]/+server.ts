import type { RequestHandler } from './$types';
import { fail, parseId } from '$lib/server/http';
import { ApiError, rsalFetch } from '$lib/server/rsal';

const KINDS = new Set(['hard', 'probability', 'uncertainty']);

/**
 * GET /api/projects/{id}/analyses/{analysisId}/exports/{kind}
 *
 * Streams one verification-checked scene product. The engine reopens the export,
 * checks its checksum and its grid before sending, and answers 409 (never a
 * silently repaired file) when either check fails.
 */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const analysisId = parseId(params.analysisId, 'analysis');
    const kind = params.kind ?? '';
    if (!KINDS.has(kind)) throw new ApiError(`Unknown scene export '${kind}'.`, 400);
    const upstream = await rsalFetch(
      `/projects/${params.id}/analyses/${analysisId}/exports/${kind}`,
    );
    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text().catch(() => '');
      throw new ApiError(detail || `Scene export failed (${upstream.status})`, upstream.status);
    }
    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') ?? 'image/tiff');
    headers.set(
      'content-disposition',
      upstream.headers.get('content-disposition') ??
        `attachment; filename="wbalc-scene-${analysisId}-${kind}.tif"`,
    );
    const sha256 = upstream.headers.get('x-rsal-export-sha256');
    const integrity = upstream.headers.get('x-rsal-export-integrity');
    if (sha256) headers.set('x-rsal-export-sha256', sha256);
    if (integrity) headers.set('x-rsal-export-integrity', integrity);
    headers.set('cache-control', 'no-store');
    return new Response(upstream.body, { status: 200, headers });
  } catch (error) {
    return fail(error);
  }
};
