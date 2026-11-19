export type Sensor = 'Sentinel-1' | 'Sentinel-2';
export type OrbitDirection = 'ascending' | 'descending';

export interface IntakeMetadata {
  acquisitionDateTime: string | null;
  sensor: Sensor | null;
  platform: string | null;
  productType: string | null;
  productLevel: string | null;
  polarization: string[];
  acquisitionMode: string | null;
  orbitDirection: OrbitDirection | null;
  relativeOrbit: number | null;
  processingBaseline: string | null;
  nativeBandResolutions: Record<string, number> | null;
  acquisitionMetadata: Record<string, unknown> | null;
  productMetadata: Record<string, unknown> | null;
  metadataFileCount: number;
}

export type Job = {
  key: string;
  date: string;
  sensor: Sensor;
  platform: string;
  files: File[];
  names: string[];
  metadata: IntakeMetadata | null;
  ignoredMerged: number;
  error?: string;
};

/** One explicit confirmation can safely cover only identical ordered schemas. */
export function bandSchemaKey(sensor: Sensor, names: string[]): string {
  return JSON.stringify([sensor, names.map(name => name.trim().toLowerCase())]);
}

const radarOrder = ['vv', 'vh', 'hh', 'hv'];
const opticalOrder = [
  'coastal', 'blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3',
  'nir', 'nir08', 'nir_narrow', 'water_vapor', 'cirrus', 'swir1', 'swir16', 'swir2', 'swir22', 'scl',
];
const sentinel2: Record<string, string> = {
  b01: 'coastal', b02: 'blue', b03: 'green', b04: 'red', b05: 'rededge1',
  b06: 'rededge2', b07: 'rededge3', b08: 'nir08', b8: 'nir08', b8a: 'nir_narrow',
  b09: 'water_vapor', b10: 'cirrus', b11: 'swir16', b12: 'swir22',
};
const bandAliases: Record<string, string> = {
  nir_08: 'nir08', nir08: 'nir08', nir8: 'nir08', nir: 'nir',
  swir_16: 'swir16', swir16: 'swir16', swir1: 'swir1',
  swir_22: 'swir22', swir22: 'swir22', swir2: 'swir2',
  scene_classification: 'scl', sceneclassification: 'scl', scl: 'scl',
};
const metadataByteLimit = 1024 * 1024;

type JsonObject = Record<string, unknown>;
type DateCandidate = { value: string; day: string; timed: boolean; priority: number };
type MetadataDocument = { name: string; raw: JsonObject };

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function strings(value: unknown): string[] {
  const values = Array.isArray(value) ? value : [value];
  return values.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).map(item => item.trim());
}

function unique(values: string[]): string[] {
  return [...new Set(values.map(value => value.trim()).filter(Boolean))];
}

function normalizePlatform(value: string): string {
  const match = /sentinel[\s_-]*([12])[\s_-]*([ab])/i.exec(value.trim());
  return match ? `Sentinel-${match[1]}${match[2].toUpperCase()}` : value.trim();
}

function sensorFromText(value: string): Sensor | null {
  const compact = value.toLowerCase().replace(/[^a-z0-9]/g, '');
  if (/sentinel1|s1[ab]|sar.?c|sentinel1grd/.test(compact)) return 'Sentinel-1';
  if (/sentinel2|s2[ab]|msi/.test(compact)) return 'Sentinel-2';
  return null;
}

function metadataDate(value: unknown, priority: number): DateCandidate | 'invalid' | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  const text = value.trim();
  const inputDay = folderDate(text.slice(0, 10));
  if (!inputDay) return 'invalid';
  if (text.length === 10) return { value: `${inputDay}T00:00:00Z`, day: inputDay, timed: false, priority };
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/i.test(text)) return 'invalid';
  const parsed = Date.parse(text);
  if (!Number.isFinite(parsed)) return 'invalid';
  // Date preserves only milliseconds. Reattach any additional fractional digits
  // after converting the timestamp (including non-UTC offsets) to canonical UTC.
  const fraction = /\.(\d+)(?=Z|[+-]\d{2}:\d{2}$)/i.exec(text)?.[1];
  let normalizedValue = new Date(parsed).toISOString();
  if (fraction && fraction.length > 3) normalizedValue = normalizedValue.replace(/\.\d{3}Z$/i, `.${fraction}Z`);
  const day = normalizedValue.slice(0, 10);
  return { value: normalizedValue, day, timed: true, priority };
}

function productSection(raw: JsonObject): JsonObject {
  const metadata = isObject(raw.METADATA) ? raw.METADATA : isObject(raw.metadata) ? raw.metadata : raw;
  const product = isObject(metadata.PRODUCT_METADATA)
    ? metadata.PRODUCT_METADATA
    : isObject(metadata.product_metadata) ? metadata.product_metadata
      : isObject(raw.PRODUCT_METADATA) ? raw.PRODUCT_METADATA
        : isObject(raw.product_metadata) ? raw.product_metadata : {};
  return product;
}

function firstString(objects: JsonObject[], keys: string[]): string | null {
  for (const object of objects) {
    for (const key of keys) {
      const value = object[key];
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
  }
  return null;
}

function chooseDate(documents: MetadataDocument[]): { value: string | null; error?: string } {
  const candidates: DateCandidate[] = [];
  let invalid = false;
  for (const { raw } of documents) {
    const properties = isObject(raw.properties) ? raw.properties : {};
    const product = productSection(raw);
    const fields: [JsonObject, string[], number][] = [
      [properties, ['datetime'], 120],
      [raw, ['datetime'], 110],
      [properties, ['acquisition_datetime', 'acquisition_date', 'date'], 100],
      [raw, ['acquisition_datetime', 'acquisition_date', 'date'], 90],
      [properties, ['start_datetime', 'start_time'], 80],
      [raw, ['start_datetime', 'start_time'], 70],
      [raw, ['ACQUISITION_DATETIME', 'ACQUISITION_DATE', 'DATE_ACQUIRED'], 65],
      [product, ['ACQUISITION_DATETIME', 'ACQUISITION_DATE_TIME', 'ACQUISITION_DATE', 'DATE_ACQUIRED', 'SENSING_TIME'], 60],
    ];
    for (const [source, keys, priority] of fields) {
      for (const key of keys) {
        if (!(key in source) || source[key] == null || source[key] === '') continue;
        const parsed = metadataDate(source[key], priority);
        if (parsed === 'invalid') invalid = true;
        else if (parsed) candidates.push(parsed);
      }
    }
  }
  if (invalid) return { value: null, error: 'dateInvalid' };
  const days = unique(candidates.map(candidate => candidate.day));
  if (days.length > 1) return { value: null, error: 'dateConflict' };
  const timed = candidates.filter(candidate => candidate.timed);
  const highestPriority = Math.max(-1, ...timed.map(candidate => candidate.priority));
  const preferredTimes = unique(timed.filter(candidate => candidate.priority === highestPriority).map(candidate => candidate.value));
  if (preferredTimes.length > 1) return { value: null, error: 'metadataConflict' };
  const chosen = timed.find(candidate => candidate.priority === highestPriority) ??
    candidates.sort((a, b) => b.priority - a.priority)[0];
  return { value: chosen?.value ?? null };
}

function productMetadataFor(documents: MetadataDocument[]): JsonObject | null {
  const values = documents.map(({ raw }) => productSection(raw)).filter(value => Object.keys(value).length > 0);
  if (!values.length) return null;
  return values.length === 1 ? values[0] : { documents: values };
}

function numeric(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function extractMetadata(documents: MetadataDocument[]): { metadata: IntakeMetadata | null; error?: string } {
  if (!documents.length) return { metadata: null };
  const date = chooseDate(documents);
  const records = documents.map(({ raw }) => {
    const properties = isObject(raw.properties) ? raw.properties : {};
    const product = productSection(raw);
    return { raw, properties, product };
  });
  const platforms = unique(records.flatMap(({ raw, properties, product }) =>
    [raw.platform, raw.PLATFORM, properties.platform, properties.PLATFORM, product.platform, product.PLATFORM]
      .flatMap(value => strings(value)).map(normalizePlatform)));
  const sensors = [...new Set(records.flatMap(({ raw, properties, product }) =>
    [raw.constellation, raw.CONSTELLATION, properties.constellation, properties.CONSTELLATION,
      raw.sensor, raw.SENSOR, properties.sensor, properties.SENSOR, raw.platform, raw.PLATFORM,
      properties.platform, properties.PLATFORM, product.platform, product.PLATFORM, product.sensor, product.SENSOR]
      .flatMap(value => strings(value)).map(sensorFromText).filter((value): value is Sensor => value !== null)))];
  const polarizations = unique(records.flatMap(({ raw, properties, product }) =>
    [properties.polarizations, properties['sar:polarizations'], properties.transmitterReceiverPolarisation,
      raw.polarizations, raw.POLARIZATIONS, raw.transmitterReceiverPolarisation,
      product.POLARIZATIONS, product.TRANSMITTER_RECEIVER_POLARISATION]
      .flatMap(value => strings(value).flatMap(item => item.split(/[\s,;/]+/)))
      .map(value => value.toUpperCase()).filter(value => ['VV', 'VH', 'HH', 'HV'].includes(value)))).sort();
  const ordered = records.flatMap(({ raw, properties, product }) => [properties, raw, product]);
  const orbit = firstString(ordered, ['orbit_state', 'sat:orbit_state', 'ORBIT_STATE', 'orbit_direction', 'ORBIT_DIRECTION'])?.toLowerCase();
  const relativeOrbitValue = ordered.map(source => source.relative_orbit ?? source.relativeOrbit ?? source['sat:relative_orbit'] ??
    source.RELATIVE_ORBIT ?? source.RELATIVE_ORBIT_NUMBER).find(value => value != null);
  const parsedRelativeOrbit = numeric(relativeOrbitValue);
  const nativeValue = ordered.map(source => source.native_band_resolutions ?? source.NATIVE_BAND_RESOLUTIONS)
    .find(isObject);
  let nativeBandResolutions: Record<string, number> | null = null;
  if (nativeValue) {
    const entries = Object.entries(nativeValue).map(([key, value]) => [key, numeric(value)] as const);
    if (entries.length && entries.every(([, value]) => value != null && value > 0)) {
      nativeBandResolutions = Object.fromEntries(entries as [string, number][]);
    }
  }
  const rawMetadata: JsonObject = documents.length === 1
    ? documents[0].raw
    : { documents: documents.map(({ name, raw }) => ({ filename: name, metadata: raw })) };
  const productMetadata = productMetadataFor(documents);
  const metadata: IntakeMetadata = {
    acquisitionDateTime: date.value,
    sensor: sensors.length === 1 ? sensors[0] : null,
    platform: platforms.length === 1 ? platforms[0] : null,
    productType: firstString(ordered, ['product_type', 'sar:product_type', 's2:product_type', 'PRODUCT_TYPE']),
    productLevel: firstString(ordered, ['processing_level', 'product_level', 'PROCESSING_LEVEL']),
    polarization: polarizations,
    acquisitionMode: firstString(ordered, ['instrument_mode', 'sar:instrument_mode', 'INSTRUMENT_MODE']),
    orbitDirection: orbit === 'ascending' || orbit === 'descending' ? orbit : null,
    relativeOrbit: parsedRelativeOrbit != null && Number.isInteger(parsedRelativeOrbit) && parsedRelativeOrbit >= 1
      ? parsedRelativeOrbit : null,
    processingBaseline: firstString(ordered, ['processing_baseline', 's2:processing_baseline', 'PROCESSING_BASELINE']),
    nativeBandResolutions,
    acquisitionMetadata: rawMetadata,
    productMetadata,
    metadataFileCount: documents.length,
  };
  if (platforms.length > 1 || sensors.length > 1) return { metadata, error: 'metadataConflict' };
  return { metadata, error: date.error };
}

async function readMetadata(files: File[]): Promise<{ metadata: IntakeMetadata | null; error?: string }> {
  const candidates = files.filter(file => /\.json$/i.test(file.name));
  if (!candidates.length) return { metadata: null };
  if (candidates.some(file => file.size > metadataByteLimit)) return { metadata: null, error: 'metadataTooLarge' };
  const documents: MetadataDocument[] = [];
  for (const file of candidates) {
    try {
      const raw: unknown = JSON.parse(await file.text());
      if (!isObject(raw)) return { metadata: null, error: 'metadataInvalid' };
      documents.push({ name: file.name, raw });
    } catch {
      return { metadata: null, error: 'metadataInvalid' };
    }
  }
  return extractMetadata(documents);
}

function isRaster(file: File): boolean {
  return /\.tiff?$/i.test(file.name);
}

function isMergedProduct(file: File): boolean {
  const stem = file.name.replace(/\.tiff?$/i, '').toLowerCase();
  return /(?:^|[_-])merged(?:$|[_-])/.test(stem);
}

function orderBands(pairs: { file: File; name: string }[], sensor: Sensor) {
  const order = sensor === 'Sentinel-1' ? radarOrder : opticalOrder;
  pairs.sort((a, b) => {
    const aIndex = order.indexOf(a.name);
    const bIndex = order.indexOf(b.name);
    const aRank = aIndex < 0 ? order.length : aIndex;
    const bRank = bIndex < 0 ? order.length : bIndex;
    return aRank - bRank || a.file.name.localeCompare(b.file.name);
  });
}

export function inferBand(filename: string) {
  const stem = filename.replace(/\.tiff?$/i, '').toLowerCase();
  const pieces = stem.split(/[^a-z0-9]+/).filter(Boolean);
  const candidates = [stem, ...pieces];
  for (const candidate of candidates) {
    if (radarOrder.includes(candidate)) return candidate;
    if (opticalOrder.includes(candidate)) return candidate;
    if (bandAliases[candidate]) return bandAliases[candidate];
    if (sentinel2[candidate]) return sentinel2[candidate];
  }
  return '';
}

export function folderDate(value: string): string {
  const matches = [...value.matchAll(/(?:^|[^\d])(\d{4})[-_]?(\d{2})[-_]?(\d{2})(?=$|[^\d])/g)];
  const valid = unique(matches.flatMap(match => {
    const day = `${match[1]}-${match[2]}-${match[3]}`;
    const time = new Date(`${day}T00:00:00Z`);
    return Number.isFinite(+time) && time.toISOString().slice(0, 10) === day ? [day] : [];
  }));
  return valid.length === 1 ? valid[0] : '';
}

function folderTimestamp(day: string): string {
  return day ? `${day}T00:00:00Z` : '';
}

function bandPairs(files: File[]) {
  return files.map(file => ({ file, name: inferBand(file.name) }));
}

function sensorForBands(pairs: { name: string }[], metadata: IntakeMetadata | null): { sensor: Sensor; mixed: boolean } {
  const hasRadar = pairs.some(pair => radarOrder.includes(pair.name));
  const hasOptical = pairs.some(pair => opticalOrder.includes(pair.name));
  return {
    sensor: hasRadar ? 'Sentinel-1' : hasOptical ? 'Sentinel-2' : metadata?.sensor ?? 'Sentinel-2',
    mixed: hasRadar && hasOptical,
  };
}

export async function planFolder(files: File[]): Promise<Job[]> {
  const groups = new Map<string, File[]>();
  for (const file of files) {
    const parts = (file.webkitRelativePath || file.name).split('/');
    parts.pop();
    const dated = parts.reduce((last, part, index) => folderDate(part) ? index : last, -1);
    const key = parts.slice(0, dated < 0 ? parts.length : dated + 1).join('/');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(file);
  }
  const planned: (Job | null)[] = await Promise.all([...groups].filter(([, group]) => group.some(isRaster)).sort(([a], [b]) => a.localeCompare(b)).map(async ([key, group]): Promise<Job | null> => {
    const allRasters = group.filter(isRaster);
    const excluded = allRasters.filter(isMergedProduct);
    const rasters = allRasters.filter(file => !isMergedProduct(file));
    if (!rasters.length) return null;
    const read = await readMetadata(group);
    const folderDay = folderDate(key.split('/').at(-1) ?? '');
    const dateDay = read.metadata?.acquisitionDateTime?.slice(0, 10) ?? '';
    let error = read.error;
    if (folderDay && dateDay && folderDay !== dateDay) error = 'dateConflict';
    const date = read.metadata?.acquisitionDateTime || folderTimestamp(folderDay);
    const pairs = bandPairs(rasters);
    const detected = sensorForBands(pairs, read.metadata);
    if (detected.mixed) error = 'mixedSensor';
    if (read.metadata?.sensor && detected.sensor !== read.metadata.sensor && pairs.some(pair => pair.name)) error = 'metadataConflict';
    orderBands(pairs, detected.sensor);
    return {
      key,
      date,
      platform: read.metadata?.platform ?? '',
      sensor: detected.sensor,
      files: pairs.map(pair => pair.file),
      names: pairs.map(pair => pair.name),
      metadata: read.metadata,
      ignoredMerged: excluded.length,
      ...(error ? { error } : {}),
    };
  }));
  return planned.filter((job): job is Job => job !== null);
}

export async function planManual(files: File[]): Promise<Job[]> {
  const allRasters = files.filter(isRaster);
  const excluded = allRasters.filter(isMergedProduct);
  const rasters = allRasters.filter(file => !isMergedProduct(file));
  if (!rasters.length) return [];
  const read = await readMetadata(files);
  const pairs = bandPairs(rasters);
  const detected = sensorForBands(pairs, read.metadata);
  let error = read.error;
  if (detected.mixed) error = 'mixedSensor';
  if (read.metadata?.sensor && detected.sensor !== read.metadata.sensor && pairs.some(pair => pair.name)) error = 'metadataConflict';
  orderBands(pairs, detected.sensor);
  return [{
    key: 'manual',
    date: read.metadata?.acquisitionDateTime ?? '',
    platform: read.metadata?.platform ?? '',
    sensor: detected.sensor,
    files: pairs.map(pair => pair.file),
    names: pairs.map(pair => pair.name),
    metadata: read.metadata,
    ignoredMerged: excluded.length,
    error,
  }];
}

export function validNames(names: string[]) {
  const clean = names.map(name => name.trim().toLowerCase());
  return clean.length > 0 && clean.every(name => name && !name.includes(',') && name.length <= 64) && new Set(clean).size === clean.length;
}
