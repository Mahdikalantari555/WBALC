import type { RequestHandler } from './$types';
import { toComparison, toExperiment } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import {
  rsalDelete,
  rsalGet,
  rsalJson,
  type RsalComparison,
  type RsalExperiment,
} from '$lib/server/rsal';

/** GET /api/projects/{id}/experiments/{experimentId} — group plus its comparison. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const [experiments, comparison] = await Promise.all([
      rsalGet<RsalExperiment[]>(`/projects/${params.id}/experiments`),
      rsalGet<RsalComparison>(`/projects/${params.id}/experiments/${params.experimentId}/compare`).catch(
        () => null,
      ),
    ]);
    const experiment = experiments.find((entry) => String(entry.id) === params.experimentId);
    if (!experiment) return fail(new Error('Experiment not found.'));
    return ok({
      experiment: toExperiment(experiment),
      comparison: comparison ? toComparison(comparison) : null,
    });
  } catch (error) {
    return fail(error);
  }
};

/**
 * PATCH — add or remove run membership. The engine writes only the association,
 * so grouping can never rewrite a run's manifest or its score.
 */
export const PATCH: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as { addRunIds?: string[]; removeRunId?: string };
    if (body.removeRunId) {
      const experiment = await rsalJson<RsalExperiment>(
        `/projects/${params.id}/experiments/${params.experimentId}/runs/${body.removeRunId}`,
        { method: 'DELETE' },
      );
      return ok(toExperiment(experiment));
    }
    const experiment = await rsalJson<RsalExperiment>(
      `/projects/${params.id}/experiments/${params.experimentId}/runs`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ training_run_ids: (body.addRunIds ?? []).map(Number) }),
      },
    );
    return ok(toExperiment(experiment));
  } catch (error) {
    return fail(error);
  }
};

/** DELETE — drops the grouping only; the runs keep their history. */
export const DELETE: RequestHandler = async ({ params }) => {
  try {
    await rsalDelete(`/projects/${params.id}/experiments/${params.experimentId}`);
    return ok({ deleted: true });
  } catch (error) {
    return fail(error);
  }
};
