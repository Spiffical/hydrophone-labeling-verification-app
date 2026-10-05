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

// Just enough DOM for the toolbar and an empty box list to render.
class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.childNodes = [];
    this.attributes = {};
    this.style = { setProperty() {} };
    this.className = '';
    this.hidden = false;
    this.disabled = false;
    this.scrollTop = 0;
    this.parentNode = null;
    this.listeners = {};
    const self = this;
    this.classList = {
      contains: name => self.className.split(/\s+/).includes(name),
      toggle: (name, on) => {
        const names = self.className.split(/\s+/).filter(Boolean).filter(n => n !== name);
        self.className = (on === undefined ? !self.classList.contains(name) : on) ? names.concat(name).join(' ') : names.join(' ');
      },
    };
  }
  set textContent(value) { this.childNodes = value ? [String(value)] : []; }
  get textContent() { return this.childNodes.map(c => (typeof c === 'string' ? c : c.textContent)).join(''); }
  get children() { return this.childNodes.filter(c => typeof c !== 'string'); }
  get firstChild() { return this.childNodes[0] || null; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
  appendChild(child) { if (typeof child !== 'string') child.parentNode = this; this.childNodes.push(child); return child; }
  remove() { if (this.parentNode) this.parentNode.childNodes = this.parentNode.childNodes.filter(c => c !== this); }
  get nextSibling() {
    const siblings = this.parentNode ? this.parentNode.childNodes : [];
    return siblings[siblings.indexOf(this) + 1] || null;
  }
  insertBefore(child, reference) {
    if (child.parentNode) child.remove();
    child.parentNode = this;
    const at = reference ? this.childNodes.indexOf(reference) : -1;
    if (at < 0) this.childNodes.push(child); else this.childNodes.splice(at, 0, child);
    return child;
  }
  replaceWith(node) {
    const siblings = this.parentNode.childNodes;
    node.parentNode = this.parentNode;
    siblings[siblings.indexOf(this)] = node;
  }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  closest(selector) {
    const name = selector.replace(/^\[|\]$/g, '');
    for (let node = this; node; node = node.parentNode) {
      if (node.getAttribute(name) !== null) return node;
    }
    return null;
  }
  querySelector() { return null; }
  // A click on `target` as the browser delivers it to this element's listeners.
  click(target) { (this.listeners.click || []).forEach(handler => handler({ target, currentTarget: this })); }
}

function find(root, predicate) {
  for (const child of root.children) {
    if (predicate(child)) return child;
    const hit = find(child, predicate);
    if (hit) return hit;
  }
  return null;
}

function loadWithToolbar({ drawLabel = 'Bio > Humpback whale' } = {}) {
  const toolbar = new FakeElement('div');
  // The panel's inner structure already exists, as after its first render.
  const panel = new FakeElement('section');
  panel.setAttribute('data-bbox-ready', '1');
  const parts = {};
  ['header', 'bulk', 'note', 'hints', 'list'].forEach(part => { parts[part] = new FakeElement('div'); });
  panel.querySelector = selector => parts[selector.replace('.modal-bbox-', '').replace('panel__', '')] || null;
  let profileClicks = 0;
  const elements = {
    'modal-bbox-toolbar': toolbar,
    'modal-bbox-panel': panel,
    'profile-btn': { click() { profileClicks += 1; } },
  };
  const window = {
    dash_clientside: { no_update: { noUpdate: true }, set_props() {} },
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
    bboxDrawMode: {
      isOn: () => false,
      labels: () => [drawLabel],
      label: () => drawLabel,
      subscribe() {},
      toggle() {},
    },
  };
  const document = {
    getElementById: id => elements[id] || null,
    createElement: tag => new FakeElement(tag),
    createTextNode: text => String(text),
    activeElement: null,
  };
  for (const file of ['modal_pages.js', 'bbox_clientside.js', 'bbox_list.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets', file), 'utf8'), { window, document });
  }
  return {
    toolbar,
    rows: () => parts.list.children.filter(node => node.classList.contains('modal-bbox-row')),
    header: parts.header,
    bulk: parts.bulk,
    hints: parts.hints,
    panel,
    window,
    list: window.dash_clientside.bboxList,
    profileClicks: () => profileClicks,
  };
}

test('without a reviewer name the toolbar keeps Draw, switched off, and offers to add one', () => {
  // Each dashboard address keeps its own profile, so a reviewer who named
  // themselves on one dashboard opens the next one without a name.
  const { toolbar, list, profileClicks } = loadWithToolbar();
  const store = { item_id: 'clip-1', boxes: [] };
  const config = { tag_options: OPTIONS };
  const isDraw = node => node.classList.contains('modal-bbox-draw');
  const isPrompt = node => node.getAttribute('data-action') === 'open-profile';

  list.render(store, null, 'verify', 'clip-1', { name: '', email: '' }, true, config);
  assert.equal(toolbar.hidden, false);
  assert.equal(find(toolbar, isDraw).disabled, true);
  assert.match(find(toolbar, isPrompt).textContent, /Add your name to draw boxes/);
  assert.equal(find(toolbar, node => node.getAttribute('role') === 'radiogroup'), null, 'tags come with drawing');
  toolbar.click(find(toolbar, isPrompt));
  assert.equal(profileClicks(), 1, 'the prompt opens the profile dialog');

  list.render(store, null, 'verify', 'clip-1', PROFILE, true, config);
  assert.equal(find(toolbar, isDraw).disabled, false);
  assert.equal(find(toolbar, isPrompt), null);
  assert.notEqual(find(toolbar, node => node.getAttribute('role') === 'radiogroup'), null);

  // Explore mode never edits boxes, so there is nothing to offer.
  list.render(store, null, 'explore', 'clip-1', { name: '', email: '' }, true, config);
  assert.equal(toolbar.hidden, true);
});

// Tags are call types, so each set belongs to a species.
const FIN = 'Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale';
const HUMPBACK = 'Biophony > Marine mammal > Cetacean > Baleen whale > Humpback whale';
const SPECIES_CONFIG = { tag_options: OPTIONS, tag_sets: [{ label: FIN, options: OPTIONS }] };

test('tag sets apply to their species and the labels under it', () => {
  const { model } = load();
  const sets = model.normalizeTagSets(SPECIES_CONFIG);
  const values = label => Array.from(model.optionsForLabel(sets, label), option => option.value);
  assert.deepEqual(values(FIN), ['20Hz', '30Hz', '40Hz']);
  assert.deepEqual(values(FIN + ' > Song'), ['20Hz', '30Hz', '40Hz']);
  assert.deepEqual(values('fin whale'), ['20Hz', '30Hz', '40Hz']);
  assert.deepEqual(values(HUMPBACK), []);
  assert.deepEqual(values(null), []);
  // Older configs have one list for every box.
  assert.deepEqual(Array.from(model.tagOptionsFor({ tag_options: OPTIONS }, HUMPBACK), o => o.value), ['20Hz', '30Hz', '40Hz']);

  // Boxes of a species without tags are never "untagged".
  const boxes = [box(null, { label: FIN }), box('20Hz', { label: FIN }), box(null, { label: HUMPBACK })];
  const optionsFor = label => model.optionsForLabel(sets, label);
  const summary = model.summarize(boxes, optionsFor);
  assert.deepEqual([summary.total, summary.untagged, summary.taggable], [3, 1, 2]);
  assert.deepEqual(Array.from(model.untaggedIndices(boxes, optionsFor)), [0]);
});

test('the toolbar offers fin whale call types only while a fin whale label is drawn', () => {
  const chips = toolbar => find(toolbar, node => node.getAttribute('role') === 'radiogroup');
  const store = { item_id: 'clip-1', boxes: [] };

  const humpback = loadWithToolbar({ drawLabel: HUMPBACK });
  humpback.list.render(store, '20Hz', 'verify', 'clip-1', PROFILE, true, SPECIES_CONFIG);
  assert.equal(chips(humpback.toolbar), null);
  assert.equal(humpback.window.bboxPanel.handleTagKey('1'), false, 'number keys have no tags to choose');

  const fin = loadWithToolbar({ drawLabel: FIN });
  fin.list.render(store, '20Hz', 'verify', 'clip-1', PROFILE, true, SPECIES_CONFIG);
  const group = chips(fin.toolbar);
  assert.deepEqual(group.children.map(chip => chip.getAttribute('data-tag')), ['', '20Hz', '30Hz', '40Hz']);
  assert.equal(find(group, node => node.classList.contains('is-active')).getAttribute('data-tag'), '20Hz');
  assert.equal(fin.window.bboxPanel.handleTagKey('2'), true);
});

test('box rows offer tags only for species that have them', () => {
  const { rows, header, bulk, window, list } = loadWithToolbar({ drawLabel: FIN });
  const store = {
    item_id: 'clip-1',
    boxes: [box(null, { label: FIN }), box(null, { label: HUMPBACK }), box('40Hz', { label: HUMPBACK })],
  };
  list.render(store, null, 'verify', 'clip-1', PROFILE, true, SPECIES_CONFIG);
  const [fin, humpback, oldTag] = rows();
  const tags = row => find(row, node => node.classList.contains('modal-bbox-row__tags'));
  const checkbox = row => find(row, node => node.getAttribute('data-action') === 'select');

  assert.deepEqual(tags(fin).children.map(chip => chip.getAttribute('data-tag')), ['20Hz', '30Hz', '40Hz']);
  assert.equal(fin.classList.contains('is-untagged'), true);
  assert.notEqual(checkbox(fin), null);

  assert.equal(tags(humpback), null, 'no tag controls');
  assert.equal(humpback.classList.contains('is-untagged'), false);
  assert.equal(checkbox(humpback), null);
  assert.deepEqual(window.bboxPanel.describeBox(1).tag, null);
  assert.equal(window.bboxPanel.needsTag(store.boxes[1]), false);

  // A tag the species does not have stays visible, as a chip that removes it.
  assert.deepEqual(tags(oldTag).children.map(chip => chip.getAttribute('data-tag')), ['40Hz']);
  assert.notEqual(checkbox(oldTag), null);

  assert.match(header.textContent, /Untagged 1/);
  assert.equal(bulk.hidden, false);

  // A humpback-only clip has nothing to tag: no untagged count, no bulk bar.
  list.render({ item_id: 'clip-2', boxes: [box(null, { label: HUMPBACK })] }, null, 'verify', 'clip-2', PROFILE, true, SPECIES_CONFIG);
  assert.doesNotMatch(header.textContent, /Untagged/);
  assert.equal(bulk.hidden, true);
});

test('new boxes and the box editor use the tags of the box species', () => {
  const { window } = load();
  const draw = window.dash_clientside.bboxInteractions.updateBoxesFromGraph;
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 }, shapes: [] } };
  const relayout = { shapes: [{ type: 'rect', x0: 1, x1: 2, y0: 20, y1: 40 }] };
  const drawFor = label => draw(relayout, { item_id: 'clip-1', boxes: [] }, figure, { label, allow_existing: true },
    'clip-1', 'verify', PROFILE, null, '20Hz', SPECIES_CONFIG)[0].boxes[0];
  assert.equal(drawFor(FIN).tag, '20Hz');
  assert.equal('tag' in drawFor(HUMPBACK), false);

  const editorOptions = window.dash_clientside.bboxList.editorTagOptions;
  assert.deepEqual(Array.from(editorOptions(FIN, null, SPECIES_CONFIG), o => o.value), ['20Hz', '30Hz', '40Hz']);
  assert.deepEqual(Array.from(editorOptions(HUMPBACK, null, SPECIES_CONFIG)), []);
  assert.deepEqual(JSON.parse(JSON.stringify(editorOptions(HUMPBACK, '40Hz', SPECIES_CONFIG))), [{ label: '40 Hz', value: '40Hz' }]);
});

test('a box drawn on another spectrogram is added with the draw label and its tag', () => {
  const { window, list } = loadWithToolbar({ drawLabel: FIN });
  const store = { item_id: 'clip-1', boxes: [box('20Hz', { label: FIN })] };
  list.render(store, '40Hz', 'verify', 'clip-1', PROFILE, true, SPECIES_CONFIG);
  const extent = { type: 'time_freq_box', time_start_sec: 2, time_end_sec: 3, freq_min_hz: 20, freq_max_hz: 60 };
  const commands = [];
  window.dash_clientside.set_props = (id, props) => commands.push([id, props]);
  assert.equal(window.bboxPanel.addBox(extent), true);
  const command = commands[0][1].data;
  assert.equal(commands[0][0], 'modal-bbox-command-store');
  assert.deepEqual(JSON.parse(JSON.stringify(command.box)),
    { label: FIN, annotation_extent: extent, source: 'manual', decision: 'added', tag: '40Hz', tag_source: 'human', tag_scope: 'time_freq_box' });

  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 }, shapes: [] } };
  const [nextStore, nextFigure, unsaved] = list.applyCommand(command, store, figure, 'clip-1', 'verify', PROFILE);
  assert.equal(nextStore.boxes.length, 2);
  assert.equal(nextStore.boxes[1].annotation_extent.time_start_sec, 2);
  assert.ok(nextFigure.layout.shapes.some(shape => shape.name === 'bbox-1'));
  assert.deepEqual({ ...unsaved }, { dirty: true, item_id: 'clip-1' });
  // Only for the clip on screen.
  assert.deepEqual(Array.from(list.applyCommand(command, store, figure, 'clip-2', 'verify', PROFILE)),
    [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update]);
});

test('a box in another band is left off the main plot instead of flattened onto its edge', () => {
  const { window } = load();
  const { applyBoxesToFigure } = window.dash_clientside.bboxInteractions;
  // Main plot: 100 Hz - 2 kHz (in kHz). The box is 30-90 Hz, drawn on the Low panel.
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 0.1, y_max: 2, y_to_hz: 1000 }, shapes: [] } };
  const low = box('20Hz', { annotation_extent: { type: 'time_freq_box', time_start_sec: 6, time_end_sec: 8, freq_min_hz: 30, freq_max_hz: 90 } });
  const mid = box('20Hz', { annotation_extent: { type: 'time_freq_box', time_start_sec: 1, time_end_sec: 2, freq_min_hz: 50, freq_max_hz: 300 } });
  const names = applyBoxesToFigure(figure, [low, mid]).layout.shapes.map(shape => shape.name).filter(Boolean);
  assert.deepEqual(Array.from(names), ['playback-marker', 'bbox-1']);
});

test('"Delete box" in the editor removes the box being edited', () => {
  const { window, list } = load();
  const commands = [];
  window.dash_clientside.set_props = (id, props) => commands.push(props.data);
  assert.equal(list.deleteFromEditor(1, 0, 'clip-1'), false, 'the editor closes');
  assert.equal(list.deleteFromEditor(0, 0, 'clip-1'), window.dash_clientside.no_update);
  const store = { item_id: 'clip-1', boxes: [box('20Hz'), box('40Hz')] };
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 10, y_min: 5, y_max: 100 }, shapes: [] } };
  const [next, , unsaved] = list.applyCommand(commands[0], store, figure, 'clip-1', 'verify', PROFILE);
  assert.deepEqual(Array.from(next.boxes, b => b.tag), ['40Hz']);
  assert.equal(unsaved.dirty, true);
});

test('box checks flag loose boxes, boxes longer than the detector window and tags outside their band', () => {
  const { model } = load();
  const checks = {
    label: 'Bio > Fin whale',
    max_box_seconds: 3,
    detector_window_seconds: 9.6,
    tag_bands_hz: { '20Hz': [0, 35], '40Hz': [35, 1000] },
  };
  const at = (tag, start, end, low, high) => box(tag, {
    annotation_extent: { type: 'time_freq_box', time_start_sec: start, time_end_sec: end, freq_min_hz: low, freq_max_hz: high },
  });
  const kinds = b => Array.from(model.boxProblems(b, checks), problem => problem.kind);
  assert.deepEqual(kinds(at('20Hz', 1, 2.5, 15, 30)), []);
  assert.deepEqual(kinds(at('20Hz', 1, 4.5, 15, 30)), ['loose']);
  // Longer than the window: one message, the stronger one.
  assert.deepEqual(kinds(at('20Hz', 1, 12, 15, 30)), ['too_long']);
  assert.match(model.boxProblems(at('20Hz', 1, 12, 15, 30), checks)[0].text, /^11\.0 s long, more than the detector/);
  // A 20 Hz box above 35 Hz, and a 40 Hz box below it; touching the band is fine.
  assert.deepEqual(kinds(at('20Hz', 1, 2, 41, 58)), ['tag_band']);
  assert.deepEqual(kinds(at('40Hz', 1, 2, 16, 30)), ['tag_band']);
  assert.deepEqual(kinds(at('40Hz', 1, 2, 30, 50)), []);
  assert.equal(model.boxProblems(at('20Hz', 1, 2, 41, 58), checks, () => '20 Hz')[0].text,
    'Tagged 20 Hz but sits at 41–58 Hz: check the tag');
  assert.deepEqual(kinds(at('20Hz', 0, 20, 41, 58)), ['too_long', 'tag_band']);
  // Untagged boxes are already marked by the list; a tag without a band is not checked.
  assert.deepEqual(kinds(at(null, 1, 2, 41, 58)), []);
  assert.deepEqual(kinds(at('30Hz', 1, 2, 41, 58)), []);
  // Only the configured species, and nothing when the checks are off.
  assert.deepEqual(kinds(at('20Hz', 1, 12, 15, 30, ) && { ...at('20Hz', 1, 12, 15, 30), label: 'Bio > Blue whale' }), []);
  assert.deepEqual(Array.from(model.boxProblems(at('20Hz', 1, 12, 15, 30), null)), []);
});

test('item notes show until they no longer apply', () => {
  const { model } = load();
  const item = { item_id: 'clip-1', review_hints: [
    'Box at 0.5–2.1 s may start earlier',
    { text: 'Accepted as fin whale with no boxes: draw a box on each call', only_without_boxes: true },
    { text: '  ' },
    7,
  ] };
  assert.deepEqual(Array.from(model.itemHints(item, 0)), [
    'Box at 0.5–2.1 s may start earlier',
    'Accepted as fin whale with no boxes: draw a box on each call',
  ]);
  assert.deepEqual(Array.from(model.itemHints(item, 2)), ['Box at 0.5–2.1 s may start earlier']);
  assert.deepEqual(Array.from(model.itemHints({ item_id: 'clip-2' }, 0)), []);
  // Loaded items keep the notes in metadata.
  assert.deepEqual(Array.from(model.itemHints({ item_id: 'clip-3', metadata: { review_hints: ['note'] } }, 0)), ['note']);
  assert.deepEqual(Array.from(model.itemHints(null, 0)), []);
});

test('with box checks on, rows to fix are marked, counted and can be listed alone', () => {
  const { toolbar, rows, header, hints, panel, list } = loadWithToolbar({ drawLabel: FIN });
  const config = { ...SPECIES_CONFIG, box_checks: { label: FIN, max_box_seconds: 3, detector_window_seconds: 9.6, tag_bands_hz: { '20Hz': [0, 35] } } };
  const at = (tag, start, end, low, high) => box(tag, {
    label: FIN, annotation_extent: { type: 'time_freq_box', time_start_sec: start, time_end_sec: end, freq_min_hz: low, freq_max_hz: high },
  });
  const store = { item_id: 'clip-1', boxes: [at('20Hz', 1, 2, 15, 30), at('20Hz', 5, 17, 15, 30), at('20Hz', 20, 21, 41, 58)] };
  const item = { item_id: 'clip-1', review_hints: ['Box at 0.5\u20132.1 s may start earlier'] };
  list.render(store, null, 'verify', 'clip-1', PROFILE, true, config, item);
  const problem = row => row.children.find(node => node.classList && node.classList.contains('modal-bbox-row__problem'));
  assert.deepEqual(rows().map(row => row.classList.contains('has-problem')), [false, true, true]);
  assert.match(problem(rows()[1]).getAttribute('title'), /^12\.0 s long, more than the detector/);
  assert.match(problem(rows()[2]).textContent, /Check tag/);
  assert.match(header.textContent, /To fix 2/);
  assert.match(toolbar.textContent, /3 boxes .* · 2 to fix/);
  assert.equal(hints.hidden, false);
  assert.match(hints.textContent, /may start earlier/);

  // "To fix" lists only those boxes; fixing one takes it off the list.
  const filter = find(header, node => node.getAttribute('data-action') === 'filter-problems');
  // The list's click handler sits on the panel; the fake parts are not its children.
  panel.listeners.click.forEach(handler => handler({ target: filter, currentTarget: { contains: () => true } }));
  assert.deepEqual(rows().map(row => row.getAttribute('data-index')), ['1', '2']);
  const fixed = { item_id: 'clip-1', boxes: [store.boxes[0], at('20Hz', 5, 6.2, 15, 30), store.boxes[2]] };
  list.render(fixed, null, 'verify', 'clip-1', PROFILE, true, config, item);
  assert.deepEqual(rows().map(row => row.getAttribute('data-index')), ['2']);
  assert.match(header.textContent, /To fix 1/);

  // Without box checks nothing is flagged, and the notes belong to their own clip.
  list.render(store, null, 'verify', 'clip-1', PROFILE, true, SPECIES_CONFIG, { item_id: 'clip-9', review_hints: ['other'] });
  assert.deepEqual(rows().map(row => row.classList.contains('has-problem')), [false, false, false]);
  assert.doesNotMatch(header.textContent, /To fix/);
  assert.equal(hints.hidden, true);
});

test('reference boxes in the figure meta are drawn dashed after the boxes', () => {
  const { window } = load();
  const { applyBoxesToFigure } = window.dash_clientside.bboxInteractions;
  const lynn = { type: 'time_freq_box', time_start_sec: 72.252, time_end_sec: 79.176, freq_min_hz: 16.388, freq_max_hz: 33.742 };
  const figure = { data: [], layout: { meta: { x_min: 0, x_max: 300, y_min: 5, y_max: 100, reference_boxes: [lynn] }, shapes: [] } };
  const fixed = box('30Hz', { annotation_extent: { ...lynn, time_start_sec: 75.0, time_end_sec: 76.8 } });
  const shapes = applyBoxesToFigure(figure, [fixed]).layout.shapes;
  assert.deepEqual(Array.from(shapes, shape => shape.name), ['playback-marker', 'bbox-0', 'ref-box-0']);
  const reference = shapes[2];
  assert.equal(reference.editable, false);
  assert.equal(reference.line.dash, 'dash');
  assert.deepEqual([reference.x0, reference.x1], [72.252, 79.176]);
});
