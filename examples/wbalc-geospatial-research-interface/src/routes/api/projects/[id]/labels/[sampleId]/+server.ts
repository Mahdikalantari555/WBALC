import type { RequestHandler } from './$types';
import { fail } from '$lib/server/http';
import { rsalDelete } from '$lib/server/rsal';

/**
 * DELETE /api/projects/{id}/labels/{sampleId}
 *
 * Removes every stored version of the sample in the engine. The review store in
 * the browser is a cache; this is the source of truth being changed.
 */
export const DELETE: RequestHandler = async ({ params }) => {
  try {
    await rsalDelete(
      `/projects/${encodeURIComponent(params.id)}/labels/${encodeURIComponent(params.sampleId)}`,
    );
    return new Response(null, { status: 204 });
  } catch (error) {
    return fail(error);
  }
};
