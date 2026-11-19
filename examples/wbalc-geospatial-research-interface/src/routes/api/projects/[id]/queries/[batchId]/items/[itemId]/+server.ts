import type { RequestHandler } from './$types';
import { toQueryItem } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalJson, type RsalQueryItem } from '$lib/server/rsal';

interface Body {
  status?: 'pending' | 'labeled' | 'rejected' | 'deferred';
  className?: string | null;
  labelId?: string | null;
  note?: string | null;
}

const STATES = new Set(['pending', 'labeled', 'rejected', 'deferred']);

/**
 * PATCH /api/projects/{id}/queries/{batchId}/items/{itemId} — record a decision.
 *
 * Rejecting a suggestion is a real, durable decision: it is stored with its time
 * so a reopened batch shows what was already judged, not just what was labeled.
 */
export const PATCH: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json().catch(() => ({}))) as Body;
    const status = body.status ?? 'pending';
    if (!STATES.has(status)) {
      throw new Error(`Unknown decision '${String(body.status)}'.`);
    }
    const item = await rsalJson<RsalQueryItem>(
      `/projects/${params.id}/queries/${params.batchId}/items/${params.itemId}`,
      {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          status,
          class_name: body.className ?? null,
          label_id: body.labelId ? Number(body.labelId) : null,
          note: body.note ?? null,
        }),
      },
    );
    return ok(toQueryItem(item));
  } catch (error) {
    return fail(error);
  }
};
