import type { RequestHandler } from './$types';
import { fail, ok, parseId } from '$lib/server/http';
import { rsalJson } from '$lib/server/rsal';

export const GET: RequestHandler = async ({ params, request }) => {
  try {
    const id = parseId(params.id, 'project');
    const dataset = parseId(params.datasetId, 'dataset');
    const incoming = new URL(request.url).searchParams;
    const query = new URLSearchParams();
    for (const key of ['mode', 'x', 'y']) {
      const value = incoming.get(key);
      if (value !== null) query.set(key, value);
    }
    const result = await rsalJson<Record<string, unknown>>(`/projects/${id}/dataset/${dataset}/pixel?${query}`);
    return ok(result);
  } catch (error) { return fail(error); }
};
