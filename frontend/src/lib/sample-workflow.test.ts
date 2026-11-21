import { describe, expect, it } from 'vitest';
import { clampWindow } from './geo';
import { contextWindow, isPixelSample } from './sample-workflow';

describe('contextWindow', () => {
  const width = 877;
  const height = 461;

  it('expands a 1×1 pixel window into a ±32 px context window', () => {
    const window = { x0: 100, y0: 200, x1: 101, y1: 201 };
    const expanded = contextWindow(window, width, height);
    expect(expanded.x1 - expanded.x0).toBe(64);
    expect(expanded.y1 - expanded.y0).toBe(64);
    // The target pixel stays the centre of the context window.
    expect((expanded.x0 + expanded.x1) / 2).toBeCloseTo(100.5);
    expect((expanded.y0 + expanded.y1) / 2).toBeCloseTo(200.5);
  });

  it('keeps patch windows (larger than 2 px) untouched', () => {
    const window = { x0: 0, y0: 0, x1: 32, y1: 32 };
    expect(contextWindow(window, width, height)).toBe(window);
  });

  it('clamps at the raster edges without shrinking the span', () => {
    const corner = { x0: 0, y0: 0, x1: 1, y1: 1 };
    const expanded = contextWindow(corner, width, height);
    expect(expanded.x0).toBe(0);
    expect(expanded.y0).toBe(0);
    expect(expanded.x1).toBe(32);
    expect(expanded.y1).toBe(32);
    const farEdge = contextWindow({ x0: 876, y0: 460, x1: 877, y1: 461 }, width, height);
    expect(farEdge.x1).toBe(width);
    expect(farEdge.y1).toBe(height);
  });

  it('agrees with clampWindow on every corner case', () => {
    const expanded = contextWindow({ x0: 870, y0: 450, x1: 871, y1: 451 }, width, height);
    const clamped = clampWindow(
      { x0: 838, y0: 418, x1: 902, y1: 482 },
      width,
      height,
    );
    expect(expanded).toEqual(clamped);
  });
});

describe('isPixelSample', () => {
  it('marks 1×1 windows as pixel samples', () => {
    expect(isPixelSample({ x0: 5, y0: 5, x1: 6, y1: 6 })).toBe(true);
  });

  it('treats patch windows as patch samples', () => {
    expect(isPixelSample({ x0: 0, y0: 0, x1: 32, y1: 32 })).toBe(false);
  });
});
