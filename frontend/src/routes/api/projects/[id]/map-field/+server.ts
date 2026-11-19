import type { RequestHandler } from './$types';
import { toMapField } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalMapField } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/map-field?layer=hard|binary|uncertainty&method=…&dataset=…&accept_unverified_schema=true
 *
 * One grid-aligned field for the map. Uses `/predict/map`, which returns values,
 * validity and grid geometry but never the full probability tensor — the map
 * stays fast and the adapter does not reshape a large payload.
 *
 * A raster whose ordered bands cannot be proven to match the model's is refused
 * by the engine (409). The adapter forwards `accept_unverified_schema` so the UI
 * can turn that refusal into a recorded, visible override instead of silently
 * predicting on unknown bands.
 */
export const GET: RequestHandler = async ({ params, url }) => {
  try {
    const requested = url.searchParams.get('layer');
    // `binary` is the derived water product; anything else falls back to the
    // three-class source layer rather than silently returning a wrong product.
    const layer =
      requested === 'uncertainty' ? 'uncertainty' : requested === 'binary' ? 'binary' : 'hard';
    const method = url.searchParams.get('method') ?? 'entropy';
    const dataset = url.searchParams.get('dataset');
    const query = new URLSearchParams({ layer, method });
    if (dataset && /^\d+$/.test(dataset)) query.set('dataset_id', dataset);
    if (url.searchParams.get('accept_unverified_schema') === 'true') {
      query.set('accept_unverified_schema', 'true');
    }
    const field = await rsalGet<RsalMapField>(
      `/projects/${params.id}/predict/map?${query.toString()}`,
    );
    return ok(toMapField(field));
  } catch (error) {
    return fail(error);
  }
};
