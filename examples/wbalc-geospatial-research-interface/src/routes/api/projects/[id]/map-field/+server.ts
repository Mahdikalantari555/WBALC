import type { RequestHandler } from './$types';
import { toMapField } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalMapField } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/map-field?layer=hard|uncertainty&method=…&dataset=…
 *
 * One grid-aligned field for the map. Uses `/predict/map`, which returns values,
 * validity and grid geometry but never the full probability tensor — the map
 * stays fast and the adapter does not reshape a large payload.
 */
export const GET: RequestHandler = async ({ params, url }) => {
  try {
    const layer = url.searchParams.get('layer') === 'uncertainty' ? 'uncertainty' : 'hard';
    const method = url.searchParams.get('method') ?? 'entropy';
    const dataset = url.searchParams.get('dataset');
    const query = new URLSearchParams({ layer, method });
    if (dataset && /^\d+$/.test(dataset)) query.set('dataset_id', dataset);
    const field = await rsalGet<RsalMapField>(
      `/projects/${params.id}/predict/map?${query.toString()}`,
    );
    return ok(toMapField(field));
  } catch (error) {
    return fail(error);
  }
};
