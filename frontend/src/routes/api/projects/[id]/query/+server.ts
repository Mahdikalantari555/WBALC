import type { RequestHandler } from './$types';
import { toQueryBatch } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalPost, type RsalQueryResponse } from '$lib/server/rsal';

interface Body {
  strategy?: 'uncertainty' | 'diversity' | 'hybrid' | 'som' | 'random';
  method?: 'least_confidence' | 'margin' | 'entropy';
  batchSize?: number;
  datasetId?: string | null;
  /** Pool granularity override; null follows the latest checkpoint's resolution. */
  sampleResolution?: 'patch' | 'pixel' | null;
  /** Only meaningful for the random baseline; the engine records the seed. */
  seed?: number | null;
  note?: string | null;
}

/**
 * POST /api/projects/{id}/query — request one active-learning batch.
 *
 * The engine persists the batch and its items, so the returned `batchId` is the
 * durable identity of this queue. The browser copy is only a cache: it can be
 * reloaded from `/api/projects/{id}/queries/{batchId}` in any session.
 * Strategies that need a model surface the engine's own 409/422 `detail`.
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
      ...(body.sampleResolution ? { sample_resolution: body.sampleResolution } : {}),
      ...(body.seed != null && Number.isFinite(Number(body.seed))
        ? { seed: Math.max(0, Math.trunc(Number(body.seed))) }
        : {}),
      ...(body.note ? { note: String(body.note).slice(0, 2000) } : {}),
    });
    return ok(toQueryBatch(response));
  } catch (error) {
    return fail(error);
  }
};
