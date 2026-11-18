import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  applyAffine,
  assessGeoreferencing,
  cellWindow,
  datasetGeoContext,
  displayToPixel,
  gridAxis,
  invertAffine,
  overlayTransform,
  patchWindowForLabel,
  pixelRectToDisplay,
  pixelToDisplay,
  pointToCell,
  toWgs84,
  type GeoContext,
} from './geo.ts';

// A north-up UTM 31N scene: 10 m pixels, 4000 x 4000.
const utm: GeoContext = {
  crsCode: 'EPSG:32631',
  transform: [10, 0, 500000, 0, -10, 5800000],
  width: 4000,
  height: 4000,
};

// A ~2.5 km scene whose raster axes are rotated by ~36.87 degrees in map space
// (an off-nadir / along-track acquisition). Small enough that reprojection is
// affine to well under a pixel.
const rotated: GeoContext = {
  crsCode: 'EPSG:32631',
  transform: [8, 6, 500000, 6, -8, 5800000],
  width: 256,
  height: 256,
};

// The same rotation over 4000 px (~40 km). Still affine to ~0.1% of the span, so
// it stays on the basemap; the residual is what the tolerance is measured on.
const rotatedHuge: GeoContext = { ...rotated, width: 4000, height: 4000 };

const pixelSpace: GeoContext = { crsCode: null, transform: null, width: 200, height: 100 };

test('affine round trips exactly', () => {
  for (const [col, row] of [
    [0, 0],
    [3999, 3999],
    [1234.5, 987.25],
  ]) {
    const [x, y] = applyAffine(utm.transform!, col, row);
    const [c, r] = invertAffine(utm.transform!, x, y);
    assert.ok(Math.abs(c - col) < 1e-9 && Math.abs(r - row) < 1e-9);
  }
});

test('pixel <-> display round trips for every grid cell centre', () => {
  const grid = { patchSize: 32, stride: 32 };
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const cell = cellWindow(utm, grid, row, col);
      const [cx, cy] = [(cell.x0 + cell.x1) / 2, (cell.y0 + cell.y1) / 2];
      const display = pixelToDisplay(utm, cx, cy);
      const back = displayToPixel(utm, display.lng, display.lat);
      assert.ok(Math.abs(back.x - cx) < 1e-6, `x drift at ${row},${col}`);
      assert.ok(Math.abs(back.y - cy) < 1e-6, `y drift at ${row},${col}`);
    }
  }
});

test('gridAxis matches the backend make_grid clamp', () => {
  assert.deepEqual(gridAxis(4000, 32, 32).slice(-2), [3936, 3968]);
  assert.equal(gridAxis(4000, 32, 32).length, 125);
  // 1000 px is not a multiple of 32: the last cell is clamped to the edge.
  const axis = gridAxis(1000, 32, 32);
  assert.equal(axis[axis.length - 1], 968);
  assert.equal(axis.length, 32);
  assert.equal(gridAxis(20, 32, 32).length, 1); // image smaller than one patch
});

test('cell window and cell lookup agree, including the clamped edge cell', () => {
  const grid = { patchSize: 32, stride: 32 };
  for (const [row, col] of [
    [0, 0],
    [3, 5],
    [124, 124],
    [7, 0],
  ]) {
    const cell = cellWindow(utm, grid, row, col);
    const found = pointToCell(utm, grid, (cell.x0 + cell.x1) / 2, (cell.y0 + cell.y1) / 2);
    assert.deepEqual(found, { row, col });
    // A point exactly on the cell origin belongs to this cell, not its neighbour.
    assert.deepEqual(pointToCell(utm, grid, cell.x0, cell.y0), { row, col });
  }
});

test('the last grid cell covers the image edge', () => {
  const grid = { patchSize: 32, stride: 32 };
  const cell = cellWindow({ ...utm, width: 1000, height: 1000 }, grid, 31, 31);
  assert.equal(cell.x1, 1000);
  assert.equal(cell.y1, 1000);
  assert.equal(cell.x1 - cell.x0, 32);
});

test('north-up UTM stays on the basemap', () => {
  const state = assessGeoreferencing(utm);
  assert.equal(state.mode, 'map');
  assert.equal(state.reason, null);
  assert.ok(Math.abs(state.tilt) < 1, `expected a small tilt, got ${state.tilt}`);
});

test('a rotated scene is warped onto the basemap, not demoted to pixel space', () => {
  const state = assessGeoreferencing(rotated);
  assert.equal(state.mode, 'map');
  assert.ok(Math.abs(state.tilt) > 30, `expected a large tilt, got ${state.tilt}`);
  assert.ok((state.fit?.residual ?? 1) < 0.02);
});

test('the overlay fit sends every corner to its reprojected position', () => {
  const state = assessGeoreferencing(rotated);
  const [a, b, c, d, e, f] = state.fit!.matrix;
  const corners: [number, number][] = [
    [0, 0],
    [rotated.width, 0],
    [0, rotated.height],
    [rotated.width, rotated.height],
  ];
  const projected = corners.map(([col, row]) =>
    toWgs84(rotated, ...applyAffine(rotated.transform!, col, row))!,
  );
  const lngs = projected.map((p) => p[0]);
  const lats = projected.map((p) => p[1]);
  const west = Math.min(...lngs);
  const east = Math.max(...lngs);
  const north = Math.max(...lats);
  const south = Math.min(...lats);
  corners.forEach(([col, row], i) => {
    const u = a * col + b * row + c;
    const v = d * col + e * row + f;
    const painted = [west + u * (east - west), north - v * (north - south)];
    const expected = projected[i];
    // 1e-5 degrees is ~1 m, i.e. a tenth of a pixel for this scene.
    assert.ok(Math.abs(painted[0] - expected[0]) < 1e-5);
    assert.ok(Math.abs(painted[1] - expected[1]) < 1e-5);
  });
});

test('a reprojection too far from affine falls back to pixel space', () => {
  // The default tolerance is 2% of the scene span; 40 km of rotation is ~0.08%,
  // so it stays on the basemap. Tightening the tolerance must demote it.
  assert.equal(assessGeoreferencing(rotatedHuge).mode, 'map');
  const strict = assessGeoreferencing(rotatedHuge, 1e-4);
  assert.equal(strict.mode, 'pixel');
  assert.equal(strict.reason, 'non-axis-aligned');
});

test('overlay transform is null for pixel-space scenes', () => {
  assert.equal(overlayTransform(pixelSpace, 800, 800), null);
  assert.notEqual(overlayTransform(utm, 800, 800), null);
});

test('pixel-space display flips y and round trips', () => {
  assert.deepEqual(pixelToDisplay(pixelSpace, 0, 0), { lng: 0, lat: 100 });
  assert.deepEqual(displayToPixel(pixelSpace, 10, 90), { x: 10, y: 10 });
});

test('unsupported CRS and missing transform fall back to pixel space', () => {
  assert.equal(assessGeoreferencing({ ...utm, crsCode: 'EPSG:9999' }).reason, 'unsupported-crs');
  assert.equal(assessGeoreferencing(pixelSpace).reason, 'not-georeferenced');
});

test('a patch rectangle is ordered south-west to north-east', () => {
  const bbox = pixelRectToDisplay(utm, { x0: 160, y0: 96, x1: 192, y1: 128 });
  assert.ok(bbox[0] < bbox[2] && bbox[1] < bbox[3]);
  // The rectangle must contain its own corners.
  const centre = pixelToDisplay(utm, 176, 112);
  assert.ok(centre.lng > bbox[0] && centre.lng < bbox[2]);
  assert.ok(centre.lat > bbox[1] && centre.lat < bbox[3]);
});

test('dataset context ignores the placeholder CRS label', () => {
  const ctx = datasetGeoContext({
    crs: 'Not georeferenced',
    transform: null,
    width: 10,
    height: 10,
  });
  assert.equal(ctx.crsCode, null);
});

test('a saved label snaps to the patch it was clicked in, in either coordinate space', () => {
  const grid = { patchSize: 32, stride: 32 };
  // Regression: RSAL stores points as `map` (projected) or `pixel`. Recovering
  // the footprint from a map point used to treat it as WGS84, snapping to the
  // wrong patch and moving the reloaded marker.
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const cell = cellWindow(utm, grid, row, col);
      const centreX = (cell.x0 + cell.x1) / 2;
      const centreY = (cell.y0 + cell.y1) / 2;
      const [mapX, mapY] = applyAffine(utm.transform!, centreX, centreY);
      assert.deepEqual(
        patchWindowForLabel(
          utm,
          grid,
          { type: 'Point', coordinates: [centreX, centreY] },
          'pixel',
        ),
        cell,
      );
      assert.deepEqual(
        patchWindowForLabel(utm, grid, { type: 'Point', coordinates: [mapX, mapY] }, 'map'),
        cell,
      );
      assert.deepEqual(pointToCell(utm, grid, centreX, centreY), { row, col });
    }
  }
});

test('a saved pin sits at the patch centre, where the query sample was drawn', () => {
  const grid = { patchSize: 32, stride: 32 };
  const cell = cellWindow(utm, grid, 1, 2);
  const centre = pixelToDisplay(utm, (cell.x0 + cell.x1) / 2, (cell.y0 + cell.y1) / 2);
  // A label clicked near the cell's south-east corner must still reload at the
  // centre, not at the click and not at the patch origin.
  const [mapX, mapY] = applyAffine(utm.transform!, cell.x1 - 1, cell.y1 - 1);
  const window = patchWindowForLabel(utm, grid, { type: 'Point', coordinates: [mapX, mapY] }, 'map');
  assert.deepEqual(window, cell);
  const pin = pixelToDisplay(utm, (window!.x0 + window!.x1) / 2, (window!.y0 + window!.y1) / 2);
  assert.ok(Math.abs(pin.lat - centre.lat) < 1e-12 && Math.abs(pin.lng - centre.lng) < 1e-12);
  // ...and the click itself is visibly elsewhere in the cell, i.e. the snap matters.
  const clicked = pixelToDisplay(utm, cell.x1 - 1, cell.y1 - 1);
  assert.ok(Math.abs(clicked.lat - centre.lat) > 1e-6 || Math.abs(clicked.lng - centre.lng) > 1e-6);
});

test('polygons keep their extent; degenerate geometry returns null', () => {
  const grid = { patchSize: 32, stride: 32 };
  const [cx, cy] = applyAffine(utm.transform!, 3, 3);
  const [ex, ey] = applyAffine(utm.transform!, 9, 7);
  assert.deepEqual(
    patchWindowForLabel(
      utm,
      grid,
      {
        type: 'Polygon',
        coordinates: [
          [
            [cx, cy],
            [ex, cy],
            [ex, ey],
            [cx, ey],
            [cx, cy],
          ],
        ],
      },
      'map',
    ),
    { x0: 3, y0: 3, x1: 9, y1: 7 },
  );
  assert.equal(patchWindowForLabel(utm, grid, { type: 'Point', coordinates: [] }, 'map'), null);
  assert.equal(
    patchWindowForLabel(utm, grid, { type: 'Point', coordinates: [Number.NaN, 4] }, 'map'),
    null,
  );
  assert.equal(patchWindowForLabel(utm, grid, { type: 'Polygon', coordinates: [] }, 'pixel'), null);
});
