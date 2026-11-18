import type { ClassDefinition, LabelInput, SampleGeometry } from '@/types';
function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') {
        value += '"';
        i++;
      } else quoted = !quoted;
    } else if (c === ',' && !quoted) {
      row.push(value.trim());
      value = '';
    } else if ((c === '\n' || c === '\r') && !quoted) {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(value.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      value = '';
    } else value += c;
  }
  if (value || row.length) {
    row.push(value.trim());
    rows.push(row);
  }
  if (quoted) throw new Error('The CSV has an unclosed quoted field.');
  return rows;
}
export function parseLabels(
  text: string,
  filename: string,
  classes: ClassDefinition[],
): LabelInput[] {
  const make = (
    lat: unknown,
    lng: unknown,
    label: unknown,
    note: unknown,
    geometry?: SampleGeometry,
  ): LabelInput => {
    const latitude = Number(lat),
      longitude = Number(lng);
    if (
      lat == null ||
      lng == null ||
      lat === '' ||
      lng === '' ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      Math.abs(latitude) > 90 ||
      Math.abs(longitude) > 180
    )
      throw new Error('Every sample needs valid latitude and longitude in WGS84.');
    const definition = classes.find(
      (c) => c.id === String(label) || c.name.toLowerCase() === String(label).toLowerCase(),
    );
    if (!definition)
      throw new Error(`Unknown class “${String(label)}”. Class names must match your project.`);
    return {
      sampleId: `import-${crypto.randomUUID()}`,
      lat: latitude,
      lng: longitude,
      label: definition.id,
      status: 'labeled',
      note: typeof note === 'string' ? note.slice(0, 1000) : '',
      geometry: geometry ?? { type: 'Point', coordinates: [longitude, latitude] },
    };
  };
  let result: LabelInput[];
  if (/\.csv$/i.test(filename)) {
    const [header, ...rows] = csvRows(text);
    if (!header) throw new Error('This CSV is empty.');
    const keys = header.map((k) => k.toLowerCase());
    const lat = keys.findIndex((k) => ['lat', 'latitude'].includes(k)),
      lng = keys.findIndex((k) => ['lng', 'lon', 'longitude'].includes(k)),
      label = keys.findIndex((k) => ['label', 'class', 'class_name'].includes(k)),
      note = keys.indexOf('note');
    if ([lat, lng, label].some((i) => i < 0))
      throw new Error('CSV headers must include latitude, longitude, and class (or label).');
    result = rows.map((row) => make(row[lat], row[lng], row[label], row[note]));
  } else {
    const data = JSON.parse(text);
    const features =
      data.type === 'FeatureCollection' ? data.features : data.type === 'Feature' ? [data] : null;
    if (!Array.isArray(features)) throw new Error('Upload a GeoJSON Feature or FeatureCollection.');
    result = features.map(
      (feature: { geometry?: SampleGeometry; properties?: Record<string, unknown> }) => {
        const g = feature.geometry,
          p = feature.properties ?? {};
        if (g?.type === 'Point') {
          const [lng, lat] = g.coordinates as number[];
          return make(lat, lng, p.label ?? p.class ?? p.class_name, p.note, g);
        }
        if (g?.type === 'Polygon') {
          const ring = (g.coordinates as number[][][])[0];
          if (!Array.isArray(ring) || ring.length < 4)
            throw new Error('A polygon needs a closed ring of at least four coordinates.');
          return make(
            ring.reduce((a, c) => a + c[1], 0) / ring.length,
            ring.reduce((a, c) => a + c[0], 0) / ring.length,
            p.label ?? p.class ?? p.class_name,
            p.note,
            g,
          );
        }
        throw new Error('Only Point and Polygon GeoJSON features are supported.');
      },
    );
  }
  if (!result.length || result.length > 1000)
    throw new Error('Import between 1 and 1,000 labeled samples at a time.');
  return result;
}
