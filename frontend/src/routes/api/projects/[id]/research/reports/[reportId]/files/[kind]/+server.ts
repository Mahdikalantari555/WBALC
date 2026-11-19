import type { RequestHandler } from './$types';
import { fail, parseId } from '$lib/server/http';
import { ApiError, rsalFetch } from '$lib/server/rsal';

const KINDS = new Set(['json', 'csv', 'markdown']);

/**
 * GET /api/projects/{id}/research/reports/{reportId}/files/{kind}
 *
 * Streams a report artifact. The engine verifies the stored checksum first and
 * answers 409 when the file no longer matches what the record claims.
 */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const reportId = parseId(params.reportId, 'report');
    const kind = params.kind ?? '';
    if (!KINDS.has(kind)) throw new ApiError(`Unknown report artifact '${kind}'.`, 400);
    const upstream = await rsalFetch(
      `/projects/${params.id}/research/reports/${reportId}/files/${kind}`,
    );
    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text().catch(() => '');
      throw new ApiError(detail || `Report download failed (${upstream.status})`, upstream.status);
    }
    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') ?? 'application/octet-stream');
    headers.set(
      'content-disposition',
      upstream.headers.get('content-disposition') ??
        `attachment; filename="wbalc-report-${reportId}.${kind === 'markdown' ? 'md' : kind}"`,
    );
    headers.set('cache-control', 'no-store');
    return new Response(upstream.body, { status: 200, headers });
  } catch (error) {
    return fail(error);
  }
};
