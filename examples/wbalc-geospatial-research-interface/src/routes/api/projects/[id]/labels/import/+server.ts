import type { RequestHandler } from './$types';
import { fail, ok } from '$lib/server/http';
import { rsalGet, rsalJson, type RsalDataset, type RsalLabel } from '$lib/server/rsal';

interface ImportBody {
  geojson: unknown;
  classProperty?: string;
  datasetId?: string | null;
  /** Optional explicit class mapping: source value -> project class name. */
  mapping?: Record<string, string>;
  /**
   * Interpret the coordinates as the dataset's own CRS instead of WGS84.
   * GeoJSON says WGS84, but GIS exports are frequently written in the raster's
   * projected CRS; the caller must say so explicitly — nothing is guessed.
   */
  coordinateCrs?: 'EPSG:4326' | 'dataset';
}

interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

/**
 * POST /api/projects/{id}/labels/import — bulk GeoJSON label import.
 *
 * Features are sent to the engine one at a time in *map* space with
 * `coordinate_crs: EPSG:4326`, so the engine performs the reprojection into the
 * dataset CRS with rasterio. Features whose class is not in the project taxonomy
 * are skipped and reported; nothing is silently recoded, and `reed` is never
 * treated as a synonym for emergent vegetation.
 */
export const POST: RequestHandler = async ({ params, request }) => {
  try {
    const body = (await request.json()) as ImportBody;
    const featureCollection = body?.geojson as
      | { type?: string; features?: unknown[] }
      | undefined;
    const features = Array.isArray(featureCollection?.features)
      ? featureCollection!.features
      : [];
    if (!features.length) {
      return ok<ImportResult>({ imported: 0, skipped: 0, errors: ['No features in the file.'] });
    }

    const datasets = await rsalGet<RsalDataset[]>(`/projects/${params.id}/dataset`);
    const datasetId = body.datasetId ? Number(body.datasetId) : datasets.at(-1)?.id;
    if (!datasetId) {
      return ok<ImportResult>({
        imported: 0,
        skipped: features.length,
        errors: ['Import needs a registered dataset in this project.'],
      });
    }

    const classProperty = body.classProperty || 'class';
    const coordinateCrs = body.coordinateCrs === 'dataset' ? undefined : 'EPSG:4326';
    const mapping = body.mapping ?? {};
    const project = await rsalGet<{ classes: string[] }>(`/projects/${params.id}`);
    const known = new Set(project.classes);
    const result: ImportResult = { imported: 0, skipped: 0, errors: [] };

    for (const [index, raw] of features.entries()) {
      const feature = raw as {
        type?: string;
        geometry?: { type?: string; coordinates?: unknown };
        properties?: Record<string, unknown> | null;
      };
      const geometryType = feature.geometry?.type;
      if (geometryType !== 'Point' && geometryType !== 'Polygon') {
        result.skipped += 1;
        result.errors.push(`Feature ${index}: geometry ${geometryType ?? 'missing'} is not supported.`);
        continue;
      }
      const rawValue = feature.properties?.[classProperty];
      const className = typeof rawValue === 'string' ? mapping[rawValue] ?? rawValue : '';
      if (!className || !known.has(className)) {
        result.skipped += 1;
        result.errors.push(
          `Feature ${index}: class '${rawValue ?? 'unset'}' is not in the project taxonomy (${project.classes.join(', ')}).`,
        );
        continue;
      }
      try {
        await rsalJson<RsalLabel>(`/projects/${params.id}/labels`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            dataset_id: datasetId,
            geometry: { type: geometryType, coordinates: feature.geometry!.coordinates },
            class_name: className,
            coordinate_space: 'map',
            ...(coordinateCrs ? { coordinate_crs: coordinateCrs } : {}),
            sample_resolution: 'patch',
          }),
        });
        result.imported += 1;
      } catch (error) {
        result.skipped += 1;
        result.errors.push(`Feature ${index}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    return ok(result);
  } catch (error) {
    return fail(error);
  }
};
