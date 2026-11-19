import type { RequestHandler } from './$types';
import { json } from '@sveltejs/kit';
import { rsalHealth } from '$lib/server/rsal';

/**
 * GET /api/health — adapter + engine liveness.
 *
 * The engine is reported as `{ ok: false }` rather than a 5xx so the UI can show
 * an actionable banner instead of an unhandled error.
 */
export const GET: RequestHandler = async () => {
  const engine = await rsalHealth();
  return json({ adapter: true, engine: engine.ok, detail: engine.detail });
};
