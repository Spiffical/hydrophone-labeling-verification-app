const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function load() {
  // No document: the script only exposes its geometry for these tests.
  const sandbox = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/bbox_edge_resize.js'), 'utf8'), sandbox);
  return sandbox.window.bboxEdgeResize;
}

const plain = value => (value ? JSON.parse(JSON.stringify(value)) : value);
const edges = (list) => ({ left: list.includes('left'), right: list.includes('right'), top: list.includes('top'), bottom: list.includes('bottom') });

test('a press in a box\'s outer thirds or just outside an edge takes that edge; the middle is left to Plotly', () => {
  const { edgesAt } = load();
  const box = { left: 100, right: 190, top: 50, bottom: 110 };
  assert.deepEqual(plain(edgesAt(box, 101, 80)), edges(['left']));
  assert.deepEqual(plain(edgesAt(box, 189, 80)), edges(['right']));
  assert.deepEqual(plain(edgesAt(box, 145, 51)), edges(['top']));
  assert.deepEqual(plain(edgesAt(box, 145, 109)), edges(['bottom']));
  assert.deepEqual(plain(edgesAt(box, 101, 51)), edges(['left', 'top']));
  assert.deepEqual(plain(edgesAt(box, 96, 80)), edges(['left']), '4 px outside');
  assert.equal(edgesAt(box, 145, 80), null, 'middle third moves the box');
  assert.equal(edgesAt(box, 94, 80), null, '6 px outside is the plot');
});

test('a box a few pixels wide can still be taken by either edge', () => {
  // A 2.3 s call on a 300 s page is about 7 px wide.
  const { edgesAt } = load();
  const narrow = { left: 100, right: 106, top: 50, bottom: 110 };
  assert.deepEqual(plain(edgesAt(narrow, 97, 80)), edges(['left']));
  assert.deepEqual(plain(edgesAt(narrow, 110, 80)), edges(['right']));
  assert.deepEqual(plain(edgesAt(narrow, 105, 80)), edges(['right']));
  assert.equal(edgesAt(narrow, 103, 80), null, 'its middle still moves it');
  const flat = { left: 100, right: 100, top: 50, bottom: 110 };
  assert.deepEqual(plain(edgesAt(flat, 100, 80)), edges(['left']), 'one edge, not both');
});

test('the nearest edge wins between neighbouring boxes, and edges off the plot are not offered', () => {
  const { pickEdge } = load();
  const a = { name: 'bbox-0', rect: { left: 100, right: 106, top: 50, bottom: 110 } };
  const b = { name: 'bbox-1', rect: { left: 109, right: 115, top: 50, bottom: 110 } };
  assert.equal(pickEdge([a, b], 106.5, 80).name, 'bbox-0');
  assert.equal(pickEdge([a, b], 108.5, 80).name, 'bbox-1');
  assert.deepEqual(plain(pickEdge([a, b], 108.5, 80).edges), edges(['left']));
  const area = { left: 0, right: 150, top: 0, bottom: 200 };
  const clipped = { name: 'bbox-2', rect: { left: -50, right: 148, top: 50, bottom: 110 } };
  assert.equal(pickEdge([clipped], 5, 80, area), null, 'its left edge is off the plot');
  assert.deepEqual(plain(pickEdge([clipped], 145, 80, area).edges), edges(['right']));
  const pastPage = { name: 'bbox-3', rect: { left: 120, right: 160, top: 50, bottom: 110 } };
  assert.equal(pickEdge([pastPage], 148, 80, area), null, 'its right edge is on the next page');
});

test('cursors point along the edges being dragged', () => {
  const { cursorFor } = load();
  assert.equal(cursorFor(edges(['left'])), 'ew');
  assert.equal(cursorFor(edges(['bottom'])), 'ns');
  assert.equal(cursorFor(edges(['left', 'top'])), 'nwse');
  assert.equal(cursorFor(edges(['right', 'bottom'])), 'nwse');
  assert.equal(cursorFor(edges(['right', 'top'])), 'nesw');
  assert.equal(cursorFor(null), null);
});

test('a resized box stays at least 2 px across and inside the plot', () => {
  const { resizeRect } = load();
  const box = { left: 100, right: 190, top: 50, bottom: 110 };
  const bounds = { left: 0, right: 300, top: 0, bottom: 200 };
  assert.deepEqual(plain(resizeRect(box, edges(['right']), -60, 0, bounds)), { left: 100, right: 130, top: 50, bottom: 110 });
  assert.equal(resizeRect(box, edges(['right']), -500, 0, bounds).right, 102);
  assert.equal(resizeRect(box, edges(['right']), 500, 0, bounds).right, 300);
  assert.equal(resizeRect(box, edges(['left']), 500, 0, bounds).left, 188);
  assert.deepEqual(plain(resizeRect(box, edges(['right', 'top']), -10, 10, bounds)), { left: 100, right: 180, top: 60, bottom: 110 });
});

test('only the dragged edges are reported, in axis units, as Plotly reports a resize', () => {
  const { updateFor } = load();
  // 10 px per second from x = 100; 2 px per Hz, higher frequencies up.
  const geometry = {
    toClientX: v => 100 + v * 10, fromClientX: p => (p - 100) / 10,
    toClientY: v => 300 - v * 2, fromClientY: p => (300 - p) / 2,
  };
  const shape = { x0: 1, x1: 3, y0: 20, y1: 40 };
  assert.deepEqual(plain(updateFor(2, shape, edges(['right']), { left: 110, right: 125, top: 220, bottom: 260 }, geometry)),
    { 'shapes[2].x1': 2.5 });
  assert.deepEqual(plain(updateFor(2, shape, edges(['top']), { left: 110, right: 130, top: 230, bottom: 260 }, geometry)),
    { 'shapes[2].y1': 35 });
  assert.deepEqual(plain(updateFor(2, shape, edges(['left', 'bottom']), { left: 105, right: 130, top: 220, bottom: 250 }, geometry)),
    { 'shapes[2].x0': 0.5, 'shapes[2].y0': 25 });
  const reversed = { x0: 3, x1: 1, y0: 40, y1: 20 };
  assert.deepEqual(plain(updateFor(4, reversed, edges(['right', 'top']), { left: 110, right: 125, top: 230, bottom: 260 }, geometry)),
    { 'shapes[4].x0': 2.5, 'shapes[4].y0': 35 });
});
