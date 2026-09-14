const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

test('figure context excludes large arrays and does not refresh sliders for box edits', () => {
  const noUpdate = {};
  const sandbox = { window: { dash_clientside: { no_update: noUpdate } } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/modal_performance.js'), 'utf8'), sandbox);
  const extract = sandbox.window.dash_clientside.modalPerformance.figureContext;
  const heatmap = { type: 'heatmap' };
  // Reading large data at all would make this path proportional to matrix size.
  for (const key of ['z', 'x', 'y']) {
    Object.defineProperty(heatmap, key, { get() { throw Error('read matrix/axis data'); } });
  }
  const figure = { data: [heatmap], layout: { meta: { y_min: 5 }, shapes: [] } };
  Object.defineProperty(figure.layout, 'images', { get() { throw Error('read image bytes'); } });
  const [context, meta] = extract(figure, 'clip-a', null, null);
  assert.equal(context.data[0].type, 'heatmap');
  assert.equal(JSON.stringify(context).includes('"z"'), false);
  const [sameContext, sameMeta] = extract(figure, 'clip-a', context, meta);
  assert.equal(sameContext, noUpdate);
  assert.equal(sameMeta, noUpdate);
  const edited = { ...figure, layout: { ...figure.layout, shapes: [{ type: 'rect', x0: 1 }] } };
  const [updated, unchangedMeta] = extract(edited, 'clip-a', context, meta);
  assert.notEqual(updated, noUpdate);
  assert.equal(unchangedMeta, noUpdate);
  const changedRange = { ...edited, layout: { ...edited.layout, meta: { y_min: 10 } } };
  assert.notEqual(extract(changedRange, 'clip-a', updated, meta)[1], noUpdate);
  assert.notEqual(extract(figure, 'clip-b', context, meta)[1], noUpdate);
});
