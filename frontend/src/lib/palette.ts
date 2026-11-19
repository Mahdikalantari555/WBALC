/** Positional palette shared with the engine's visual exports. */
export const CLASS_COLORS = [
  '#5cbb96', '#e0a458', '#7d9bd4', '#c97b9b', '#9b8cd4', '#d4c95c',
  '#6bb8c9', '#d47b6b', '#8bc96b', '#b0b7c3', '#c9a0dc',
];

export function classColor(_name: string, index = 0): string {
  return index < 0 ? '#a4b0c2' : CLASS_COLORS[index % CLASS_COLORS.length];
}

/**
 * Colours for the *derived* binary water product.
 *
 * Deliberately not the first entries of the class palette: a binary product is a
 * different product from the three-class map, and it must not look like it.
 */
export const BINARY_COLORS: Record<'water' | 'non_water', string> = {
  water: '#3a7dd0',
  non_water: '#8a9b6a',
};

export function classColors(classes: string[]): Record<string, string> {
  const result: Record<string, string> = {};
  classes.forEach((name, index) => {
    result[name] = classColor(name, index);
  });
  return result;
}

/** The uncertainty ramp used by the map overlay and its legend. */
export const UNCERTAINTY_RAMP = ['#3c78c8', '#f0e6a8', '#e0663c'] as const;

const RAMP_RGB = UNCERTAINTY_RAMP.map(hexToRgb);

function rampRgb(t: number): number[] {
  const scaled = Math.max(0, Math.min(1, t)) * (RAMP_RGB.length - 1);
  const index = Math.min(RAMP_RGB.length - 2, Math.floor(scaled));
  const local = scaled - index;
  return RAMP_RGB[index].map((start, channel) => Math.round(start + (RAMP_RGB[index + 1][channel] - start) * local));
}

export function uncertaintyColor(value: number, min: number, max: number): string {
  return Number.isFinite(value) ? `rgb(${rampRgb((value - min) / (max - min || 1)).join(', ')})` : 'transparent';
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
  const span = max - min || 1;
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const base = (row * cols + col) * 4;
      const value = values[row][col];
      if (!valid[row]?.[col] || value === null || value === undefined) {
        pixels.data[base + 3] = 0;
        continue;
      }
      const color = rampRgb((value - min) / span);
      pixels.data[base] = color[0];
      pixels.data[base + 1] = color[1];
      pixels.data[base + 2] = color[2];
      pixels.data[base + 3] = 235;
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}
