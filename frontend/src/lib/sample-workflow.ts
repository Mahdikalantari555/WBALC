/**
 * Pixel-mode sample presentation helpers.
 *
 * A pixel-resolution query pool proposes 1×1 windows; a patch pool proposes
 * 32 px cells. Both are reviewable, but a one-pixel thumbnail is useless, so
 * pixel samples preview a clamped context window around the target instead.
 */
import type { PixelWindow } from './geo';

/** Window side (px) at or below which a sample counts as a single pixel. */
const PIXEL_WINDOW_MAX = 2;
/** Context radius around a pixel sample, in source pixels. */
const CONTEXT_PAD = 32;

export function isPixelSample(window: PixelWindow): boolean {
  return window.x1 - window.x0 <= PIXEL_WINDOW_MAX && window.y1 - window.y0 <= PIXEL_WINDOW_MAX;
}

/** The sample's own window, expanded to ±32 px for pixel samples. */
export function contextWindow(window: PixelWindow, width: number, height: number): PixelWindow {
  if (!isPixelSample(window)) return window;
  const cx = (window.x0 + window.x1) / 2;
  const cy = (window.y0 + window.y1) / 2;
  const x0 = Math.max(0, Math.min(width, Math.floor(cx - CONTEXT_PAD)));
  const y0 = Math.max(0, Math.min(height, Math.floor(cy - CONTEXT_PAD)));
  return {
    x0,
    y0,
    x1: Math.max(x0 + 1, Math.min(width, Math.ceil(cx + CONTEXT_PAD))),
    y1: Math.max(y0 + 1, Math.min(height, Math.ceil(cy + CONTEXT_PAD))),
  };
}
