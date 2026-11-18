/**
 * Painting of grid-aligned model fields (classification, uncertainty).
 *
 * One canvas pixel per grid cell, handed to Leaflet as a single image overlay:
 * the map pays nothing extra for panning or zooming, and the cells stay exactly
 * aligned with the patch footprints because both come from the same transform.
 */
import type { MapField } from '@/types';

/** Two-stop ramp for uncertainty: cool = confident, warm = uncertain. */
export const UNCERTAINTY_RAMP = ['#3c78c8', '#f0e6a8', '#e0663c'];

export function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace('#', '');
  return [
    parseInt(value.slice(0, 2), 16),
    parseInt(value.slice(2, 4), 16),
    parseInt(value.slice(4, 6), 16),
  ];
}

/** Colour of an uncertainty cell: cool = confident, warm = uncertain. */
export function uncertaintyColor(value: number): [number, number, number] {
  const t = Math.max(0, Math.min(1, value));
  const stops = UNCERTAINTY_RAMP.map(hexToRgb);
  const scaled = t * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(scaled));
  const local = scaled - index;
  return stops[index].map((channel, i) =>
    Math.round(channel + (stops[index + 1][i] - channel) * local),
  ) as [number, number, number];
}

/**
 * Render a field to a PNG data URL, one pixel per cell, with invalid cells
 * transparent. `scale` upsamples for readability; keep pixelated rendering on.
 *
 * Uncertainty is stretched over the field's own [min, max], because a trained
 * model's entropy usually spans a narrow band (e.g. 0.68-1.00) and an absolute
 * ramp would paint the whole scene one colour. The legend prints both endpoints
 * so the colour scale is never ambiguous.
 */
export function fieldToDataUrl(field: MapField, scale = 1): string | null {
  const { rows, cols } = field.grid;
  if (!rows || !cols) return null;
  const canvas = document.createElement('canvas');
  canvas.width = cols * scale;
  canvas.height = rows * scale;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const colors = field.colors.length ? field.colors.map(hexToRgb) : [];
  const pixels = ctx.createImageData(canvas.width, canvas.height);
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      if (!field.valid[row]?.[col]) continue; // stays transparent
      const value = field.values[row]?.[col];
      if (value === null || value === undefined) continue;
      const rgb =
        field.layer === 'hard'
          ? (colors[Math.round(value) % colors.length] ?? [200, 200, 200])
          : uncertaintyColor(
              field.max > field.min ? (value - field.min) / (field.max - field.min) : 1,
            );
      for (let dy = 0; dy < scale; dy++) {
        for (let dx = 0; dx < scale; dx++) {
          const base =
            ((row * scale + dy) * canvas.width + (col * scale + dx)) * 4;
          pixels.data[base] = rgb[0];
          pixels.data[base + 1] = rgb[1];
          pixels.data[base + 2] = rgb[2];
          pixels.data[base + 3] = 235;
        }
      }
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}

/** Human label for the method the field was computed with. */
export function methodLabel(method: string | null): string {
  if (method === 'least_confidence') return 'Least confidence';
  if (method === 'margin') return 'Margin';
  if (method === 'entropy') return 'Entropy';
  return '';
}

export function formatValue(value: number, layer: MapField['layer']): string {
  return layer === 'uncertainty' ? value.toFixed(2) : String(Math.round(value));
}
