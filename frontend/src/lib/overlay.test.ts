import assert from 'node:assert/strict';
import { test } from 'node:test';
import { hexToRgb, methodLabel, uncertaintyColor, UNCERTAINTY_RAMP } from './overlay.ts';
import { UNCERTAINTY_METHODS } from './layers.ts';

test('uncertainty ramp runs from confident (cool) to uncertain (warm)', () => {
  const low = uncertaintyColor(0);
  const high = uncertaintyColor(1);
  // cool = more blue than red; warm = more red than blue
  assert.ok(low[2] > low[0], `expected a cool low end, got ${low}`);
  assert.ok(high[0] > high[2], `expected a warm high end, got ${high}`);
  assert.deepEqual(low, hexToRgb(UNCERTAINTY_RAMP[0]));
  assert.deepEqual(high, hexToRgb(UNCERTAINTY_RAMP[UNCERTAINTY_RAMP.length - 1]));
});

test('ramp is continuous and stays in range', () => {
  let previous = uncertaintyColor(0);
  for (let i = 1; i <= 20; i++) {
    const current = uncertaintyColor(i / 20);
    for (let c = 0; c < 3; c++) {
      assert.ok(current[c] >= 0 && current[c] <= 255);
      // neighbouring steps must not jump by more than the ramp's own span
      assert.ok(Math.abs(current[c] - previous[c]) <= 40, `jump at ${i / 20}`);
    }
    previous = current;
  }
  // out-of-range values clamp rather than produce garbage
  assert.deepEqual(uncertaintyColor(-5), uncertaintyColor(0));
  assert.deepEqual(uncertaintyColor(5), uncertaintyColor(1));
});

test('method labels match the backend vocabulary', () => {
  for (const method of UNCERTAINTY_METHODS) {
    assert.ok(methodLabel(method).length > 0, `${method} has no label`);
  }
  assert.equal(methodLabel('least_confidence'), 'Least confidence');
  assert.equal(methodLabel(null), '');
});

test('hex parsing handles the backend palette format', () => {
  assert.deepEqual(hexToRgb('#5cbb96'), [92, 187, 150]);
  assert.deepEqual(hexToRgb('5cbb96'), [92, 187, 150]);
});
