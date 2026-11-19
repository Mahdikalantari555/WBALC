import type { RequestHandler } from './$types';
import { toTemporalSeries } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, type RsalTemporalSeries } from '$lib/server/rsal';

/**
 * GET /api/projects/{id}/temporal/series — per-date areas from each scene's
 * latest analysis. Areas are computed on each scene's own grid; the engine
 * reports differing grids as caveats rather than resampling silently.
 */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const series = await rsalGet<RsalTemporalSeries>(`/projects/${params.id}/temporal/series`);
    return ok(toTemporalSeries(series));
  } catch (error) {
    return fail(error);
  }
};
