import type { RequestHandler } from './$types';
import { toMetrics } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalMetrics } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/runs — recorded training runs, newest first.
 *
 * The engine exposes `metrics/history` (one entry per run) and, separately, a
 * `TrainResponse` for the run that just finished. History is what the arena and
 * the evaluation view read, so a score is always tied to an iteration.
 */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const history = await rsalGet<RsalMetrics[]>(`/projects/${params.id}/metrics/history`);
    const runs = history.map((metrics) => ({
      id: String(metrics.id),
      iteration: metrics.iteration,
      modelType: metrics.model_type,
      resolution: metrics.resolution,
      nSamples: metrics.n_samples,
      createdAt: metrics.created_at,
      metrics: toMetrics(metrics),
    }));
    return ok(runs.reverse());
  } catch (error) {
    return fail(error);
  }
};
