/**
 * Stable colours for project classes.
 *
 * The engine's class names are the identity (`open_water`, `emergent_vegetation`,
 * `land`, or any legacy list), so colours are assigned by name first and by
 * position second. A legend therefore keeps its colours across projects, and an
 * unknown class still gets a deterministic colour instead of a random one.
 */
const KNOWN: Record<string, string> = {
  open_water: '#4aa9ff',
  emergent_vegetation: '#65d592',
  land: '#a4b0c2',
  water: '#4aa9ff',
  vegetation: '#65d592',
  reed: '#8fdf9f',
  reeds: '#8fdf9f',
  other: '#a4b0c2',
  non_water: '#a4b0c2',
  urban: '#d99bd6',
  soil: '#d7b183',
  snow: '#dbe9f6',
  cloud: '#c3cbd6',
};

const FALLBACK = ['#4aa9ff', '#65d592', '#a4b0c2', '#f3be67', '#c9a2e8', '#8fd6d0', '#e79b9b'];

export function classColor(name: string, index = 0): string {
  const key = name.trim().toLowerCase().replace(/[\s-]+/g, '_');
  return KNOWN[key] ?? FALLBACK[index % FALLBACK.length];
}

/** Colours for a class list, in the engine's declared order. */
export function classColors(classes: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  classes.forEach((name, index) => {
    result[name] = classColor(name, index);
  });
  return result;
}

/** The uncertainty ramp used by the map overlay and its legend. */
export const UNCERTAINTY_RAMP = ['#2c4a63', '#3f7f86', '#68b9a6', '#c6c07a', '#e39a5f'] as const;

export function uncertaintyColor(value: number, min: number, max: number): string {
  if (!Number.isFinite(value)) return 'transparent';
  const span = max - min || 1;
  const t = Math.max(0, Math.min(1, (value - min) / span));
  const index = Math.min(UNCERTAINTY_RAMP.length - 1, Math.round(t * (UNCERTAINTY_RAMP.length - 1)));
  return UNCERTAINTY_RAMP[index];
}

function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace('#', '');
  const full =
    value.length === 3
      ? value
          .split('')
          .map((c) => c + c)
          .join('')
      : value;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

/**
 * Paint a hard-class grid into a PNG data URL at cell resolution.
 * Returned image is used as a Leaflet overlay; scaling is CSS-side so the
 * overlay always aligns with the raster it came from.
 */
export function renderClassOverlay(
  values: (number | null)[][],
  valid: boolean[][],
  colors: string[],
): string | null {
  if (typeof document === 'undefined' || !values.length) return null;
  const rows = values.length;
  const cols = values[0]?.length ?? 0;
  if (!cols) return null;
  const canvas = document.createElement('canvas');
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const pixels = ctx.createImageData(cols, rows);
  const rgb = colors.map(hexToRgb);
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const base = (row * cols + col) * 4;
      const index = values[row][col];
      if (!valid[row]?.[col] || index === null || index === undefined) {
        pixels.data[base + 3] = 0;
        continue;
      }
      const color = rgb[index] ?? [90, 160, 200];
      pixels.data[base] = color[0];
      pixels.data[base + 1] = color[1];
      pixels.data[base + 2] = color[2];
      pixels.data[base + 3] = 255;
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}

/** Paint an uncertainty grid into a PNG data URL using the shared ramp. */
export function renderUncertaintyOverlay(
  values: (number | null)[][],
  valid: boolean[][],
  min: number,
  max: number,
): string | null {
  if (typeof document === 'undefined' || !values.length) return null;
  const rows = values.length;
  const cols = values[0]?.length ?? 0;
  if (!cols) return null;
  const canvas = document.createElement('canvas');
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const pixels = ctx.createImageData(cols, rows);
  const ramp = UNCERTAINTY_RAMP.map(hexToRgb);
  const span = max - min || 1;
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const base = (row * cols + col) * 4;
      const value = values[row][col];
      if (!valid[row]?.[col] || value === null || value === undefined) {
        pixels.data[base + 3] = 0;
        continue;
      }
      const t = Math.max(0, Math.min(1, (value - min) / span));
      const color = ramp[Math.min(ramp.length - 1, Math.round(t * (ramp.length - 1)))];
      pixels.data[base] = color[0];
      pixels.data[base + 1] = color[1];
      pixels.data[base + 2] = color[2];
      pixels.data[base + 3] = 235;
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}
