import { NextRequest, NextResponse } from 'next/server';
import { ApiError, rsalFetch } from './rsal';

type RouteContext = { params: Promise<{ id?: string; sceneId?: string }> };

function projectId(value: string | undefined): string {
  if (!value || !/^\d+$/.test(value)) throw new ApiError('Project not found.', 404);
  return value;
}

async function forward(response: Response): Promise<NextResponse> {
  if (response.status === 204) return new NextResponse(null, { status: 204 });
  const body = await response.arrayBuffer();
  return new NextResponse(body, {
    status: response.status,
    headers: { 'content-type': response.headers.get('content-type') ?? 'application/json' },
  });
}

async function handle(operation: () => Promise<NextResponse>): Promise<NextResponse> {
  try {
    return await operation();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    const message = error instanceof Error ? error.message : 'Scene service is unavailable.';
    return NextResponse.json({ error: message }, { status });
  }
}

export async function sceneCollectionHandler(request: NextRequest, context: RouteContext) {
  return handle(async () => {
    const { id } = await context.params;
    const path = `/projects/${projectId(id)}/scenes`;
    if (request.method === 'GET') return forward(await rsalFetch(path));
    const form = await request.formData();
    return forward(await rsalFetch(path, { method: 'POST', body: form }));
  });
}

export async function sceneItemHandler(request: NextRequest, context: RouteContext) {
  return handle(async () => {
    const { id, sceneId } = await context.params;
    const path = `/projects/${projectId(id)}/scenes/${encodeURIComponent(sceneId ?? '')}`;
    return forward(await rsalFetch(path, { method: request.method }));
  });
}

export async function sceneSpatialHandler(_request: NextRequest, context: RouteContext) {
  return handle(async () => {
    const { id, sceneId } = await context.params;
    const path = `/projects/${projectId(id)}/scenes/${encodeURIComponent(sceneId ?? '')}/spatial`;
    return forward(await rsalFetch(path));
  });
}
