import type { RequestHandler } from './$types';
import { toProtocol } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import { rsalGet, rsalJson, type RsalProtocol } from '$lib/server/rsal';

/** GET /api/projects/{id}/research/protocols — declared splits with their hashes. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const protocols = await rsalGet<RsalProtocol[]>(`/projects/${params.id}/research/protocols`);
    return ok(protocols.map(toProtocol));
  } catch (error) {
    return fail(error);
  }
};

/**
 * POST /api/projects/{id}/research/protocols — declare an evaluation split.
 *
 * A split the data cannot support comes back with status `insufficient` and a
 * reason; it is stored, because "we tried and it was not possible" is a result.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as {
      name?: string;
      protocol?: 'random' | 'spatial' | 'temporal';
      seed?: number;
      testSize?: number;
      blockSize?: number;
      buffer?: number;
      groups?: Record<string, string>;
    };
    const protocol = await rsalJson<RsalProtocol>(`/projects/${params.id}/research/protocols`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name: body.name ?? '',
        protocol: body.protocol ?? 'random',
        seed: body.seed ?? 42,
        test_size: body.testSize ?? 0.3,
        block_size: body.blockSize ?? 256,
        buffer: body.buffer ?? 0,
        groups: body.groups ?? {},
      }),
    });
    return ok(toProtocol(protocol), { status: 201 });
  } catch (error) {
    return fail(error);
  }
};
