/**
 * WCAG contrast maths, in one place.
 *
 * The palette lives in `src/index.css` as oklch; these helpers convert to sRGB
 * and compute relative luminance so the contrast of every text/background pair
 * is *checked* rather than eyeballed. No browser is required, which matters:
 * this repository must be verifiable in CI.
 */

export type Rgb = readonly [number, number, number];

export function oklchToRgb(l: number, c: number, h: number): Rgb {
  const rad = (h * Math.PI) / 180;
  const a = c * Math.cos(rad);
  const b = c * Math.sin(rad);
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;
  const lm = l_ ** 3;
  const mm = m_ ** 3;
  const sm = s_ ** 3;
  const red = 4.0767416621 * lm - 3.3077115913 * mm + 0.2309699292 * sm;
  const green = -1.2684380046 * lm + 2.6097574011 * mm - 0.3413193965 * sm;
  const blue = -0.0041960863 * lm - 0.7034186147 * mm + 1.707614701 * sm;
  const gamma = (u: number): number => {
    const clamped = Math.min(1, Math.max(0, u));
    return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055;
  };
  return [gamma(red), gamma(green), gamma(blue)];
}

function channelLuminance(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance([r, g, b]: Rgb): number {
  return (
    0.2126 * channelLuminance(r) + 0.7152 * channelLuminance(g) + 0.0722 * channelLuminance(b)
  );
}

/** WCAG 2.1 contrast ratio, 1…21. */
export function contrastRatio(foreground: Rgb, background: Rgb): number {
  const a = relativeLuminance(foreground);
  const b = relativeLuminance(background);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** Parse a token value out of `src/index.css` (oklch or hex). */
export function parseColour(value: string): Rgb {
  const oklch = value.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
  if (oklch) return oklchToRgb(Number(oklch[1]), Number(oklch[2]), Number(oklch[3]));
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const int = parseInt(hex[1], 16);
    return [(int >> 16) & 255, (int >> 8) & 255, int & 255].map((v) => v / 255) as unknown as Rgb;
  }
  throw new Error(`unparseable colour: ${value}`);
}
