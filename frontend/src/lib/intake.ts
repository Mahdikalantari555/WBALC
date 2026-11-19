export type Sensor = 'Sentinel-1' | 'Sentinel-2';
export type Job = { key: string; date: string; sensor: Sensor; platform: string; files: File[]; names: string[]; error?: string };

const optical = ['blue', 'green', 'red', 'nir', 'rededge1', 'rededge2', 'rededge3', 'nir_narrow', 'swir1', 'swir2'];
const radar = ['vv', 'vh', 'hh', 'hv'];
const sentinel2: Record<string, string> = { b02:'blue', b03:'green', b04:'red', b05:'rededge1', b06:'rededge2', b07:'rededge3', b08:'nir', b8a:'nir_narrow', b11:'swir1', b12:'swir2' };

export function inferBand(filename: string) {
  const stem = filename.replace(/\.tiff?$/i, '').toLowerCase();
  const pieces = stem.split(/[^a-z0-9]+/);
  return [...optical, ...radar].find(name => name === stem || pieces.includes(name)) ??
    pieces.map(piece => sentinel2[piece]).find(Boolean) ?? '';
}

export function folderDate(value: string): string {
  const m = /^(\d{4})[-_]?(\d{2})[-_]?(\d{2})$/.exec(value);
  if (!m) return '';
  const date = `${m[1]}-${m[2]}-${m[3]}`;
  const time = new Date(`${date}T00:00:00Z`);
  return Number.isFinite(+time) && time.toISOString().slice(0, 10) === date ? date : '';
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
  return Promise.all([...groups].filter(([, files]) => files.some(f => /\.tiff?$/i.test(f.name))).sort(([a], [b]) => a.localeCompare(b)).map(async ([key, group]) => {
    const rasters = group.filter(f => /\.tiff?$/i.test(f.name));
    const metadata = group.filter(f => /\.json$/i.test(f.name) && f.size <= 1024 * 1024);
    const date = folderDate(key.split('/').at(-1) ?? '');
    let timestamp = date ? `${date}T00:00:00Z` : '';
    let platform = '';
    let error: string | undefined;
    const times = new Set<string>();
    const platforms = new Set<string>();
    for (const file of metadata) {
      try {
        const data = JSON.parse(await file.text());
        const props = data?.properties ?? data;
        const stamp = props?.datetime ?? props?.acquisition_datetime ?? props?.acquisition_date ?? props?.date;
        if (typeof stamp === 'string') {
          const day = folderDate(stamp.slice(0, 10));
          if (!day || (stamp.length > 10 && (!/(?:Z|[+-]\d\d:\d\d)$/i.test(stamp) || !Number.isFinite(Date.parse(stamp))))) error = 'dateInvalid';
          else if (date && day !== date) error = 'dateConflict';
          else times.add(stamp.length === 10 ? `${day}T00:00:00Z` : new Date(stamp).toISOString());
        }
        if (typeof props?.platform === 'string') platforms.add(props.platform);
      } catch { error = 'metadataInvalid'; }
    }
    if (times.size > 1 || platforms.size > 1) error = 'metadataConflict';
    if (times.size === 1) timestamp = [...times][0];
    if (platforms.size === 1) platform = [...platforms][0];
    const pairs = rasters.map(file => ({ file, name: inferBand(file.name) }));
    const hasRadar = pairs.some(p => radar.includes(p.name));
    const order = hasRadar ? radar : optical;
    if (hasRadar && pairs.some(p => optical.includes(p.name))) error = 'mixedSensor';
    if (!timestamp) error ??= 'dateInvalid';
    pairs.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name) || a.file.name.localeCompare(b.file.name));
    return { key, date: timestamp, platform, sensor: hasRadar ? 'Sentinel-1' : 'Sentinel-2', error,
      files: pairs.map(p => p.file), names: pairs.map(p => p.name) };
  }));
}

export function validNames(names: string[]) {
  const clean = names.map(name => name.trim().toLocaleLowerCase());
  return clean.length > 0 && clean.every(name => name && !name.includes(',') && name.length <= 64) && new Set(clean).size === clean.length;
}
