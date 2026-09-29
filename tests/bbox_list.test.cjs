const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const OPTIONS = [
  { label: '20 Hz', value: '20Hz' },
  { label: '30 Hz', value: '30Hz' },
  { label: '40 Hz', value: '40Hz' },
];
const PROFILE = { name: 'Tester', email: 'tester@example.com' };

function box(tag, extra = {}) {
  const value = {
    label: 'Bio > Fin whale',
    annotation_extent: { type: 'time_freq_box', time_start_sec: 1, time_end_sec: 2, freq_min_hz: 15, freq_max_hz: 30 },
    source: 'manual',
    decision: 'added',
    ...extra,
  };
  if (tag) value.tag = tag;
  return value;
}

// Loads the assets the way the browser does (alphabetical: bbox_*, then modal_pages.js;
// the order does not matter as they only use each other at call time).
function load() {
  const noUpdate = { noUpdate: true };
  const calls = [];
  const sandbox = {
    window: {
      dash_clientside: { no_update: noUpdate, set_props: (id, props) => calls.push([id, props]) },
      requestAnimationFrame: () => 1,
      cancelAnimationFrame: () => {},
    },
    // No modal is mounted in these tests, so rendering is a no-op.
    document: { getElementById: () => null, activeElement: null },
  };
  for (const file of ['modal_pages.js', 'bbox_clientside.js', 'bbox_list.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets', file), 'utf8'), sandbox);
  }
  const { window } = sandbox;
  return { window, noUpdate, calls, model: window.bboxListModel, list: window.dash_clientside.bboxList };
}

test('summary counts tags, untagged boxes and tags missing from the option list', () => {
  const { model } = load();
  const summary = model.summarize([box('20Hz'), box('20Hz'), box(null), box('old-tag'), box('  ')], OPTIONS);
  assert.equal(summary.total, 5);
  assert.equal(summary.untagged, 2);
  assert.deepEqual(JSON.parse(JSON.stringify(summary.tags)), [
    { value: '20Hz', label: '20 Hz', count: 2 },
    { value: '30Hz', label: '30 Hz', count: 0 },
    { value: '40Hz', label: '40 Hz', count: 0 },
    { value: 'old-tag', label: 'old-tag', count: 1 },
  ]);
  assert.deepEqual(Array.from(model.untaggedIndices([box('20Hz'), box(null), box('')])), [1, 2]);
});

test('applyTag sets and clears tags without mutating the input', () => {
  const { model } = load();
  const boxes = [box('20Hz'), box(null), box('40Hz')];
  const before = JSON.stringify(boxes);
  const set = model.applyTag(boxes, [0, 1, 7, -1, 'x'], '30Hz');
  assert.equal(set.changed, 2);
  assert.deepEqual(set.boxes.map(b => b.tag), ['30Hz', '30Hz', '40Hz']);
  const cleared = model.applyTag(set.boxes, [2], null);
  assert.equal(cleared.changed, 1);
  assert.equal('tag' in cleared.boxes[2], false);
  assert.equal(model.applyTag(boxes, [0], '20Hz').changed, 0);
  assert.equal(JSON.stringify(boxes), before);
});

test('applyTagChanges applies every change in one command', () => {
  // Several quick clicks can reach applyCommand as one coalesced command.
  const { model } = load();
  const result = model.applyTagChanges([box('20Hz'), box('20Hz'), box('20Hz')], [[0, '40Hz'], [1, '30Hz'], [0, '40Hz'], ['bad']]);
  assert.equal(result.changed, 2);
  assert.deepEqual(result.boxes.map(b => b.tag), ['40Hz', '30Hz', '20Hz']);
});

test('number keys map to tag options and 0 means no tag', () => {
  const { model } = load();
  assert.equal(model.tagForKey('0', OPTIONS), null);
  assert.equal(model.tagForKey('1', OPTIONS), '20Hz');
  assert.equal(model.tagForKey('3', OPTIONS), '40Hz');
  assert.equal(model.tagForKey('4', OPTIONS), undefined);
  assert.equal(model.tagForKey('e', OPTIONS), undefined);
});

test('extents are described compactly in seconds and Hz or kHz', () => {
  const { model } = load();
  assert.deepEqual({ ...model.describeExtent(box(null).annotation_extent) }, { time: '1.0–2.0 s', freq: '15–30 Hz' });
  assert.equal(model.describeExtent({ time_start_sec: 3, time_end_sec: 4, freq_min_hz: 2000, freq_max_hz: 16000 }).freq, '2.0–16.0 kHz');
  assert.deepEqual({ ...model.describeExtent({ type: 'clip' }) }, { time: 'Whole clip', freq: 'All frequencies' });
});

test('applyCommand tags boxes, redraws overlays and marks the clip unsaved', () => {
  const { list, noUpdate } = load();
  const store = { item_id: 'clip-1', boxes: [box('20Hz'), box(null)] };
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 } } };
  const command = { action: 'set_tags', item_id: 'clip-1', changes: [[1, '40Hz'], [0, null]] };
  const [nextStore, nextFigure, unsaved] = list.applyCommand(command, store, figure, 'clip-1', 'verify', PROFILE);
  assert.deepEqual(nextStore.boxes.map(b => b.tag || null), [null, '40Hz']);
  assert.equal(store.boxes[1].tag, undefined, 'input store is not mutated');
  const editHandles = nextFigure.data.find(trace => trace.name === '__bbox_edit_handle__');
  assert.deepEqual(Array.from(editHandles.customdata), [0, 1]);
  assert.equal(editHandles.hoverinfo, 'none', 'no Plotly hover label on the handles');
  assert.deepEqual({ ...unsaved }, { dirty: true, item_id: 'clip-1' });

  const unchanged = result => result.length === 3 && result.every(value => value === noUpdate);
  assert.ok(unchanged(list.applyCommand({ ...command, item_id: 'other' }, store, figure, 'clip-1', 'verify', PROFILE)));
  assert.ok(unchanged(list.applyCommand(command, store, figure, 'clip-1', 'explore', PROFILE)));
  assert.ok(unchanged(list.applyCommand(command, store, figure, 'clip-1', 'verify', { name: 'No email' })));
  assert.ok(unchanged(list.applyCommand({ ...command, changes: [[0, '20Hz']] }, store, figure, 'clip-1', 'verify', PROFILE)));
});

test('number keys choose the tag for new boxes only while the list is editable', () => {
  const { window, list, calls } = load();
  const config = { tag_options: OPTIONS, bulk_tagging: true };
  const store = { item_id: 'clip-1', boxes: [] };
  list.render(store, null, 'explore', 'clip-1', PROFILE, true, config);
  assert.equal(window.bboxPanel.handleTagKey('2'), false);
  list.render(store, null, 'verify', 'clip-1', PROFILE, true, config);
  assert.equal(window.bboxPanel.handleTagKey('2'), true);
  assert.equal(window.bboxPanel.handleTagKey('7'), false);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['modal-bbox-active-tag-store', { data: '30Hz' }]]);
});

test('hover details and edit requests use the current clip boxes', () => {
  const { window, list, calls } = load();
  const store = { item_id: 'clip-1', boxes: [box('40Hz'), box(null)] };
  list.render(store, null, 'verify', 'clip-1', PROFILE, true, { tag_options: OPTIONS });
  assert.deepEqual({ ...window.bboxPanel.describeBox(0) }, {
    title: 'Box 1', tag: '40 Hz', untagged: false, detail: 'Fin whale · 1.0–2.0 s · 15–30 Hz',
  });
  assert.equal(window.bboxPanel.describeBox(1).tag, 'No tag');
  assert.equal(window.bboxPanel.describeBox(1).untagged, true);
  assert.equal(window.bboxPanel.describeBox(5), null);

  assert.equal(window.bboxPanel.openEditor(1), true);
  assert.equal(window.bboxPanel.openEditor(9), false);
  const [id, props] = calls[0];
  assert.equal(id, 'modal-bbox-edit-request-store');
  assert.deepEqual([props.data.item_id, props.data.index], ['clip-1', 1]);
});

test('figure boxes carry no titles but keep the source label and a box index', () => {
  const { window } = load();
  const figure = {
    data: [],
    layout: {
      meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 },
      annotations: [{ name: '__spectrogram_source__', text: 'Source: generated from audio' }, { text: 'Box 1: old title' }],
    },
  };
  const next = window.dash_clientside.bboxInteractions.applyBoxesToFigure(figure, [box('20Hz'), box('40Hz')]);
  assert.deepEqual(Array.from(next.layout.annotations, a => a.text), ['Source: generated from audio']);
  assert.deepEqual(Array.from(next.layout.shapes, s => s.name), ['playback-marker', 'bbox-0', 'bbox-1']);
});

test('new boxes drawn on the spectrogram get the chosen tag if the dashboard offers it', () => {
  const { window } = load();
  const draw = window.dash_clientside.bboxInteractions.updateBoxesFromGraph;
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 }, shapes: [] } };
  const relayout = { shapes: [{ type: 'rect', x0: 1, x1: 2, y0: 20, y1: 40 }] };
  const target = { label: 'Bio > Fin whale', allow_existing: true };
  const drawWith = (tag) => draw(relayout, { item_id: 'clip-1', boxes: [] }, figure, target, 'clip-1', 'verify',
    PROFILE, null, tag, { tag_options: OPTIONS })[0].boxes[0];
  assert.equal(drawWith('40Hz').tag, '40Hz');
  assert.equal('tag' in drawWith(null), false);
  assert.equal('tag' in drawWith('not-offered'), false);
});

test('graph clicks only delete the box whose handles are shown', () => {
  // Handles are hidden unless their box is hovered, but Plotly still reports
  // clicks at their positions; bbox_hover_affordances.js publishes the hovered box.
  const { window } = load();
  const { applyBoxesToFigure, deleteBox } = window.dash_clientside.bboxInteractions;
  const base = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 } } };
  const store = { item_id: 'clip-1', boxes: [box('20Hz'), box('40Hz', { annotation_extent: { type: 'time_freq_box', time_start_sec: 5, time_end_sec: 6, freq_min_hz: 40, freq_max_hz: 60 } })] };
  const figure = applyBoxesToFigure(base, store.boxes);
  const curve = figure.data.findIndex(trace => trace.name === '__bbox_delete_handle__');
  const clickOn = index => ({ points: [{ curveNumber: curve, pointNumber: index, customdata: index }] });
  const remove = index => deleteBox(clickOn(index), store, figure, 'clip-1', 'verify', PROFILE, null, { dirty: false })[0];

  window.bboxHover = { activeBox: 1 };
  assert.equal(remove(0), window.dash_clientside.no_update, 'hidden handle of box 1 is ignored');
  assert.deepEqual(remove(1).boxes.map(b => b.tag), ['20Hz']);
  window.bboxHover = { activeBox: null };
  assert.equal(remove(1), window.dash_clientside.no_update, 'nothing hovered, nothing deleted');
});

test('in draw mode a new box keeps the label active and the draw tool selected', () => {
  const { window } = load();
  const { updateBoxesFromGraph, applyBoxesToFigure } = window.dash_clientside.bboxInteractions;
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 }, shapes: [] } };
  const relayout = { shapes: [{ type: 'rect', x0: 1, x1: 2, y0: 20, y1: 40 }] };
  const target = { label: 'Bio > Fin whale', allow_existing: true };
  const draw = () => updateBoxesFromGraph(relayout, { item_id: 'clip-1', boxes: [] }, figure, target, 'clip-1',
    'verify', PROFILE, null, null, { tag_options: OPTIONS });

  const [, oneShotFigure, oneShotLabel] = draw();
  assert.equal(oneShotLabel, null, 'a single + click draws one box');
  assert.equal(oneShotFigure.layout.dragmode, 'pan');

  window.bboxDraw.sticky = true;
  const [, stickyFigure, stickyLabel] = draw();
  assert.equal(stickyLabel, window.dash_clientside.no_update, 'label stays active for the next drag');
  assert.equal(stickyFigure.layout.dragmode, 'drawrect');
  assert.equal(applyBoxesToFigure(figure, []).layout.dragmode, 'drawrect');
});

test('on a long clip shown in pages, box handles stay beside their box on its page', () => {
  const { window } = load();
  const { applyBoxesToFigure } = window.dash_clientside.bboxInteractions;
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 1394, y_min: 5, y_max: 100, page_seconds: 300 }, shapes: [] } };
  const near = (start, end) => box('20Hz', { annotation_extent: { type: 'time_freq_box', time_start_sec: start, time_end_sec: end, freq_min_hz: 15, freq_max_hz: 30 } });
  const out = applyBoxesToFigure(figure, [near(296, 299), near(1000, 1004)]);
  for (const trace of out.data) {
    const [first, second] = Array.from(trace.x);
    assert.ok(first > 0 && first < 300 && Math.abs(first - 297.5) < 12, trace.name + ' ' + first);
    assert.ok(second > 900 && second < 1200 && Math.abs(second - 1002) < 12, trace.name + ' ' + second);
  }
  assert.equal(out.layout.meta.handle_page_seconds, 300);
});

test('a reviewer tag is recorded as a human box tag, even over a model tag', () => {
  const { model } = load();
  const modelTagged = box('20Hz', { tag_source: 'model', tag_scope: 'time_freq_box' });
  const [retagged] = model.applyTag([modelTagged], [0], '40Hz').boxes;
  assert.deepEqual([retagged.tag, retagged.tag_source, retagged.tag_scope], ['40Hz', 'human', 'time_freq_box']);
  const [cleared] = model.applyTag([retagged], [0], null).boxes;
  assert.deepEqual([cleared.tag, cleared.tag_source, cleared.tag_scope], [undefined, undefined, undefined]);
});
