import type { RequestHandler } from './$types';
import { toLabel } from '$lib/server/adapter';
import { fail, ok } from '$lib/server/http';
import {
  ApiError,
  rsalGet,
  rsalJson,
  type RsalDataset,
  type RsalLabel,
  type RsalLabelBatchResponse,
} from '$lib/server/rsal';

async function datasetLookup(projectId: string) {
  const datasets = await rsalGet<RsalDataset[]>(`/projects/${projectId}/dataset`);
  return { datasets, lookup: new Map(datasets.map((dataset) => [dataset.id, dataset])) };
}

/** GET /api/projects/{id}/labels — current (latest-version) labels. */
export const GET: RequestHandler = async ({ params }) => {
  try {
    const [{ lookup }, labels] = await Promise.all([
      datasetLookup(params.id),
      rsalGet<RsalLabel[]>(`/projects/${params.id}/labels`),
    ]);
    return ok(labels.map((label) => toLabel(label, lookup)));
  } catch (error) {
    return fail(error);
  }
};

interface SubmitBody {
  sampleId: string;
  datasetId: string;
  className: string;
  /** Patch centre in source pixels; the label is a point in pixel space. */
  col: number;
  row: number;
  iteration?: number;
  /** Revision of a label that already exists, so the engine versions it. */
  revise?: boolean;
  autoTrain?: boolean;
  modelType?: 'rf' | 'lightgbm';
  /** Set when the operator is answering a durable query item. */
  queryBatchId?: string | null;
  queryItemId?: string | null;
}

/**
 * POST /api/projects/{id}/labels — store one reviewed sample.
 *
 * The label is submitted in *pixel* space with the query batch's own
 * `sample_id`, so re-submitting a corrected class creates a new version of the
 * same sample instead of a second, unrelated label. When `queryItemId` is given,
 * the engine links this version to that durable item and marks it labeled.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as SubmitBody;
    if (!body?.sampleId) throw new ApiError('sampleId is required.', 400);
    if (!body.className) throw new ApiError('className is required.', 400);
    if (!Number.isFinite(Number(body.col)) || !Number.isFinite(Number(body.row))) {
      throw new ApiError('A sampled patch needs finite pixel coordinates.', 400);
    }
    const payload = {
      sample_id: body.sampleId,
      dataset_id: body.datasetId ? Number(body.datasetId) : null,
      geometry: { type: 'Point' as const, coordinates: [Number(body.col), Number(body.row)] },
      class_name: body.className,
      iteration: Math.max(0, Number(body.iteration ?? 0)),
      coordinate_space: 'pixel' as const,
      sample_resolution: 'patch' as const,
      // Only sent when the label really came from a query item; otherwise the
      // engine records manual provenance, which is the truthful answer.
      ...(body.queryItemId
        ? {
            query_batch_id: body.queryBatchId ? Number(body.queryBatchId) : null,
            query_item_id: Number(body.queryItemId),
          }
        : {}),
    };
    const response = await rsalJson<RsalLabel | RsalLabelBatchResponse>(
      `/projects/${params.id}/labels`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      },
    );
    const stored = 'labels' in response ? response.labels[0] : response;
    const { lookup } = await datasetLookup(params.id);
    return ok(toLabel(stored, lookup));
  } catch (error) {
    return fail(error);
  }
};
