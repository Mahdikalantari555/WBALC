import type { RequestHandler } from './$types';
import { toReport } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, rsalJson, type RsalReport } from '$lib/server/rsal';

/** GET /api/projects/{id}/research/reports — generated bundles, oldest first. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const reports = await rsalGet<RsalReport[]>(`/projects/${params.id}/research/reports`);
    return ok(reports.map(toReport));
  } catch (error) {
    return fail(error);
  }
};

/** POST /api/projects/{id}/research/reports — regenerate a bundle from stored records. */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json().catch(() => ({}))) as { title?: string };
    const report = await rsalJson<RsalReport>(`/projects/${params.id}/research/reports`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title: body.title ?? '' }),
    });
    return ok(toReport(report), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
