import type { RequestHandler } from './$types';
import { toQueryBatch } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalPost, type RsalQueryResponse } from '$lib/server/rsal';

interface Body {
  strategy?: 'uncertainty' | 'diversity' | 'hybrid' | 'som';
  method?: 'least_confidence' | 'margin' | 'entropy';
  batchSize?: number;
  datasetId?: string | null;
}

/**
 * POST /api/projects/{id}/query — request one active-learning batch.
 *
 * The engine is stateless here, so the returned batch becomes the browser-side
 * review queue (persisted per project). Strategies that need a model surface the
 * engine's own 409/422 `detail` verbatim.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json().catch(() => ({}))) as Body;
    const response = await rsalPost<RsalQueryResponse>(`/projects/${params.id}/query`, {
      strategy: body.strategy ?? 'diversity',
      method: body.method ?? 'least_confidence',
      batch_size: Math.min(200, Math.max(1, Number(body.batchSize ?? 20))),
      dataset_id: body.datasetId ? Number(body.datasetId) : null,
      exclude_labeled: true,
    });
    return ok(toQueryBatch(response));
  } catch (error) {
    return fail(error);
  }
};
