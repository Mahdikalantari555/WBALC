import type { RequestHandler } from './$types';
import { toExperiment } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, rsalJson, type RsalExperiment } from '$lib/server/rsal';

/** GET /api/projects/{id}/experiments — named run groups, newest first. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const experiments = await rsalGet<RsalExperiment[]>(`/projects/${params.id}/experiments`);
    return ok(experiments.map(toExperiment));
  } catch (error) {
    return fail(error);
  }
};

/** POST /api/projects/{id}/experiments — create a named group. */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      name?: string;
      description?: string;
      hypothesis?: string | null;
      runIds?: string[];
    };
    if (!body?.name?.trim()) throw new Error('An experiment needs a name.');
    const experiment = await rsalJson<RsalExperiment>(`/projects/${params.id}/experiments`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name: body.name.trim(),
        description: body.description ?? '',
        hypothesis: body.hypothesis ?? null,
      }),
    });
    if (body.runIds?.length) {
      const withRuns = await rsalJson<RsalExperiment>(
        `/projects/${params.id}/experiments/${experiment.id}/runs`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ training_run_ids: body.runIds.map(Number) }),
        },
      );
      return ok(toExperiment(withRuns), { status: 201 });
    }
    return ok(toExperiment(experiment), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
