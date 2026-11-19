import type { RequestHandler } from './$types';
import { toQueryHistory } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalQueryBatch } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/queries — durable sampling history, newest first.
 *
 * Project-scoped and identity-free: batches record what was sampled and why,
 * never who sampled it (this application has no auth model).
 */
export const GET: RequestHandler = async ({ params, url }) => {
  try {
    const limit = Math.min(200, Math.max(1, Number(url.searchParams.get('limit') ?? 25)));
    const batches = await rsalGet<RsalQueryBatch[]>(`/projects/${params.id}/queries?limit=${limit}`);
    return ok(
      batches.map((batch) => {
        const entry = toQueryHistory(batch);
        // List entries carry counts, not every item.
        return { ...entry, items: [] as typeof entry.items };
      }),
    );
  } catch (error) {
    return fail(error);
  }
};
