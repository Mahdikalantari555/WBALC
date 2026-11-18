/** Shared response/error helpers for the adapter route handlers. */
import { json } from '@sveltejs/kit';
import { ApiError } from './rsal';

export function ok<T>(data: T, init?: ResponseInit) {
  return json(data, init);
}

export function fail(error: unknown) {
  if (error instanceof ApiError) {
    return json({ message: error.message, status: error.status }, { status: error.status });
  }
  const message = error instanceof Error ? error.message : String(error);
  return json({ message, status: 500 }, { status: 500 });
}

/** Validate a numeric path segment, so `/api/projects/abc` is a 404 not a 500. */
export function parseId(value: string | undefined, label = 'resource'): string {
  if (!value || !/^\d+$/.test(value)) {
    throw new ApiError(`Unknown ${label}.`, 404);
  }
  return value;
}
