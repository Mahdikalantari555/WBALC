export interface StudyAreaInput {
  geometry: Record<string, unknown>;
  crs: string;
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : null;
}

function crsName(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  const crs = object(value);
  const properties = object(crs?.properties);
  const candidate = properties?.name ?? crs?.name ?? properties?.href ?? crs?.href;
  return typeof candidate === 'string' && candidate.trim() ? candidate.trim() : null;
}

function normalizeCrs(value: unknown): string {
  if (value == null) return 'EPSG:4326'; // RFC 7946 GeoJSON is WGS84 when no legacy CRS is declared.
  const name = crsName(value);
  if (!name) throw new Error('GeoJSON CRS declaration is invalid.');
  if (/crs:?84$/i.test(name)) return 'EPSG:4326';
  const epsg = /EPSG(?:[:/]+)(?:0[/:])?(\d+)\s*$/i.exec(name);
  if (epsg) return `EPSG:${epsg[1]}`;
  return name;
}

function asPolygonParts(geometry: JsonObject): unknown[][] {
  if (geometry.type === 'Polygon') {
    if (!Array.isArray(geometry.coordinates)) throw new Error('Invalid Polygon coordinates.');
    return [geometry.coordinates];
  }
  if (geometry.type === 'MultiPolygon') {
    if (!Array.isArray(geometry.coordinates)) throw new Error('Invalid MultiPolygon coordinates.');
    return geometry.coordinates;
  }
  throw new Error('Study area must contain only Polygon or MultiPolygon features.');
}

function validatePolygons(polygons: unknown[][]) {
  if (!polygons.length) throw new Error('Study area has no polygon coordinates.');
  for (const polygon of polygons) {
    if (!Array.isArray(polygon) || !polygon.length) throw new Error('A polygon must contain at least one ring.');
    for (const ring of polygon) {
      if (!Array.isArray(ring) || ring.length < 4) throw new Error('Polygon rings need at least four positions.');
      const positions = ring.map(position => {
        if (!Array.isArray(position) || position.length < 2 ||
            !position.every(coordinate => typeof coordinate === 'number' && Number.isFinite(coordinate))) {
          throw new Error('Polygon positions must contain finite numeric coordinates.');
        }
        return position as number[];
      });
      const first = positions[0];
      const last = positions.at(-1);
      if (positions.some(position => position.length !== first.length)) {
        throw new Error('Polygon ring positions must use a consistent coordinate dimension.');
      }
      if (first.length !== last?.length || !first.every((coordinate, index) => coordinate === last[index])) {
        throw new Error('Polygon rings must be closed.');
      }
    }
  }
}

/** Convert GeoJSON Geometry, Feature or FeatureCollection into the API's area geometry. */
export function normalizeStudyArea(value: unknown): StudyAreaInput {
  const root = object(value);
  if (!root) throw new Error('Invalid GeoJSON object.');
  const crsDeclarations: unknown[] = [];
  if (root.crs != null) crsDeclarations.push(root.crs);
  if (root.type === 'FeatureCollection' && Array.isArray(root.features)) {
    for (const feature of root.features) {
      const item = object(feature);
      if (item?.crs != null) crsDeclarations.push(item.crs);
    }
  }
  const normalizedCrs = [...new Set(crsDeclarations.map(normalizeCrs))];
  if (normalizedCrs.length > 1) throw new Error('GeoJSON features use different coordinate reference systems.');
  let geometry: JsonObject;

  if (root.type === 'Feature') {
    const featureGeometry = object(root.geometry);
    if (!featureGeometry) throw new Error('GeoJSON Feature has no polygon geometry.');
    geometry = featureGeometry;
  } else if (root.type === 'FeatureCollection') {
    if (!Array.isArray(root.features) || !root.features.length) throw new Error('GeoJSON FeatureCollection is empty.');
    const features = root.features.map(object);
    if (features.some(feature => !feature || feature.type !== 'Feature')) throw new Error('Invalid GeoJSON FeatureCollection.');
    const geometries = features.map(feature => object(feature!.geometry));
    if (geometries.some(featureGeometry => !featureGeometry)) throw new Error('A GeoJSON Feature has no geometry.');
    if (geometries.length === 1) {
      geometry = geometries[0]!;
    } else {
      const polygons = geometries.flatMap(featureGeometry => asPolygonParts(featureGeometry!));
      geometry = { type: 'MultiPolygon', coordinates: polygons };
    }
  } else if (root.type === 'Polygon' || root.type === 'MultiPolygon') {
    geometry = root;
  } else if (object(root.geometry)?.type === 'Polygon' || object(root.geometry)?.type === 'MultiPolygon') {
    // Accept common wrappers used by GIS tools around a single geometry.
    geometry = object(root.geometry)!;
  } else {
    throw new Error('GeoJSON must be a Polygon, MultiPolygon, Feature, or FeatureCollection.');
  }

  const polygons = asPolygonParts(geometry);
  validatePolygons(polygons);
  return { geometry, crs: normalizedCrs[0] ?? 'EPSG:4326' };
}
