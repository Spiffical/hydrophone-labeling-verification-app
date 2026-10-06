const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// A main spectrogram with a colour bar (plot area 101-946 px on the page) and
// one other range under it, as the modal lays them out. Plot areas start 100 px
// down the page.
function plot({ left, width, size, range, yRange, yType = 'linear', meta = {} }) {
  const handlers = {};
  const listeners = {};
  const gd = {
    layout: { meta },
    _fullLayout: { _size: size, xaxis: { range }, yaxis: { type: yType, range: yRange }, dragmode: false },
    // Already showing the clip's (no) boxes.
    _rangePanelShapes: '[]',
    _rangePanelLayout: null,
    getBoundingClientRect: () => ({ left, right: left + width, width, top: 100 }),
    on(name, handler) { handlers[name] = handler; },
    addEventListener(name, handler) { listeners[name] = handler; },
    handlers,
    listeners,
  };
  gd._rangePanelLayout = gd.layout;
  return gd;
}

function load({ panelLeft = 44, panelWidth = 1006, panelSize = { l: 70, r: 36, w: 900 }, panelRange = [0, 9.75],
  panelYRange = [5, 125], panelYType = 'linear', boxes = [], drawing = false } = {}) {
  const main = plot({ left: 44, width: 1006, size: { l: 57, r: 104, w: 845 }, range: [2, 4] });
  // The Low range (5-125 Hz) of a 10 s clip.
  const panel = plot({ left: panelLeft, width: panelWidth, size: panelSize, range: panelRange,
    yRange: panelYRange, yType: panelYType,
    meta: { range_id: 'low', freq_min_hz: 5, freq_max_hz: 125, x_min: 0, x_max: 10, x_to_seconds: 1 } });
  const relayouts = [];
  const targets = [];
  const added = [];
  let drawSubscriber = null;
  const window = {
    bboxPanel: { boxes: () => boxes, canEdit: () => true, addBox: extent => { added.push(extent); return true; } },
    bboxDrawMode: { isOn: () => drawing, subscribe: fn => { drawSubscriber = fn; } },
    // Runs at once; returns no frame id, so the next schedule() runs too.
    requestAnimationFrame: callback => { callback(); return null; },
    Plotly: {
      relayout(gd, update) {
        if ('dragmode' in update) gd._fullLayout.dragmode = update.dragmode;
        relayouts.push(JSON.parse(JSON.stringify(update)));
        targets.push(gd === main ? 'main' : 'panel');
        return Promise.resolve();
      },
    },
  };
  const documentListeners = {};
  const document = {
    documentElement: {},
    getElementById: () => null,
    querySelector: selector => (selector.includes('modal-image-graph') ? main : null),
    querySelectorAll: selector => (selector.includes('spectrogram-modal-range-graph') ? [panel] : []),
    addEventListener: (name, handler) => { documentListeners[name] = handler; },
  };
  class MutationObserver { observe() {} }
  for (const file of ['bbox_clientside.js', 'modal_range_panels.js', 'modal_scroll_zoom.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets', file), 'utf8'), {
      window, document, MutationObserver,
    });
  }
  return { window, main, panel, relayouts, targets, added, documentListeners, setDrawing: on => { drawing = on; }, drawSubscriber: () => drawSubscriber };
}

// A panel lined up with the main plot (plot area 101-946 px across, 112-400 px down).
const LINED_UP = { panelSize: { l: 57, r: 104, w: 845, t: 12, h: 288 }, panelRange: [2, 4] };
const STEP_IN = Math.exp(-0.1); // Plotly's largest scroll step, one wheel notch

// A wheel event over the panel, handled by modal_scroll_zoom.js.
function wheelAt(s, across, up, deltaY) {
  const event = {
    target: { closest: selector => (selector.includes('spectrogram-modal-range-graph') ? s.panel : null) },
    clientX: 101 + 845 * across, clientY: 400 - 288 * up, deltaY,
    prevented: false, preventDefault() { this.prevented = true; },
  };
  s.documentListeners.wheel(event);
  return event;
}

const near = (actual, expected) => assert.ok(
  actual.length === expected.length && actual.every((value, index) => Math.abs(value - expected[index]) < 1e-9),
  JSON.stringify(actual) + ' vs ' + JSON.stringify(expected));

test('other ranges take the main plot\'s plot-area edges and time window', () => {
  const { window, relayouts } = load();
  window.modalRangePanels.sync();
  assert.deepEqual(relayouts, [{ 'margin.l': 57, 'margin.r': 104, 'xaxis.range': [2, 4] }]);
});

test('a panel already in line is left alone', () => {
  const { window, relayouts } = load({ panelSize: { l: 57, r: 104, w: 845 }, panelRange: [2, 4] });
  window.modalRangePanels.sync();
  assert.deepEqual(relayouts, []);
});

test('a panel off screen still follows the time window', () => {
  const { window, relayouts } = load({ panelWidth: 0 });
  window.modalRangePanels.sync();
  assert.deepEqual(relayouts, [{ 'xaxis.range': [2, 4] }]);
});

test('panels follow the main plot as it pages, zooms and redraws', () => {
  const { window, main, panel, relayouts } = load();
  window.modalRangePanels.sync();
  assert.equal(typeof panel.handlers.plotly_afterplot, 'function', 'a new figure from the server is realigned');
  main._fullLayout.xaxis.range = [300, 600];
  panel._fullLayout._size = { l: 57, r: 104, w: 845 };
  panel._fullLayout.xaxis.range = [2, 4];
  main.handlers.plotly_relayout();
  assert.deepEqual(relayouts[1], { 'xaxis.range': [300, 600] });
});

const FIN = 'Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale';
const extentBox = (t0, t1, f0, f1) => ({ label: FIN, annotation_extent: { type: 'time_freq_box', time_start_sec: t0, time_end_sec: t1, freq_min_hz: f0, freq_max_hz: f1 } });

test('each panel shows the boxes that reach into its band', () => {
  const boxes = [
    extentBox(1, 2, 15, 30),        // inside the Low band
    extentBox(3, 4, 100, 400),      // partly inside
    extentBox(5, 6, 2000, 3000),    // above it
    { label: FIN, annotation_extent: { type: 'time_range', time_start_sec: 7, time_end_sec: 8 } },
  ];
  const { window, panel } = load({ boxes });
  const shapes = window.modalRangePanels.panelShapes(panel, boxes);
  assert.deepEqual(Array.from(shapes, shape => shape.name), ['panel-box-0', 'panel-box-1', 'panel-box-3']);
  // Parts outside the band are left to the plot area to cut off.
  assert.deepEqual([shapes[1].y0, shapes[1].y1], [100, 400]);
  assert.deepEqual([shapes[2].y0, shapes[2].y1], [5, 125]);
  assert.equal(shapes[0].editable, false);
  window.modalRangePanels.sync();
});

test('in draw mode a drag on a panel adds a box in seconds and Hz', () => {
  const s = load({ drawing: true });
  s.window.modalRangePanels.sync();
  assert.equal(s.relayouts.at(-1).dragmode, 'drawrect', 'panels draw while draw mode is on');
  // Plotly reports the drawn (unnamed) shape with the panel's own ones.
  s.panel.handlers.plotly_relayout({ shapes: [{ type: 'rect', x0: 2.25, x1: 3.5, y0: 20, y1: 60 }] });
  assert.deepEqual(JSON.parse(JSON.stringify(s.added)), [
    { type: 'time_freq_box', time_start_sec: 2.25, time_end_sec: 3.5, freq_min_hz: 20, freq_max_hz: 60 },
  ]);
  // A box the band's full height stays within the band.
  const full = s.window.modalRangePanels.extentFromPanelShape(s.panel, { x0: 1, x1: 2, y0: 5, y1: 125 });
  assert.deepEqual(JSON.parse(JSON.stringify(full)),
    { type: 'time_freq_box', time_start_sec: 1, time_end_sec: 2, freq_min_hz: 5, freq_max_hz: 125 });
  // The panel's own shapes coming back from a relayout are not new boxes.
  s.panel.handlers.plotly_relayout({ shapes: [{ name: 'panel-box-0', x0: 1, x1: 2, y0: 5, y1: 6 }] });
  assert.equal(s.added.length, 1);

  s.setDrawing(false);
  s.drawSubscriber()();
  assert.equal(s.relayouts.at(-1).dragmode, false);
});

test('a figure from the server gets its boxes back', () => {
  const boxes = [extentBox(1, 2, 15, 30)];
  const s = load({ boxes });
  s.window.modalRangePanels.sync();
  const applied = s.relayouts.filter(update => update.shapes).length;
  s.window.modalRangePanels.sync();
  assert.equal(s.relayouts.filter(update => update.shapes).length, applied, 'nothing to redo');
  s.panel.layout = { meta: s.panel.layout.meta };  // Plotly.react with a new figure
  s.window.modalRangePanels.sync();
  assert.equal(s.relayouts.filter(update => update.shapes).length, applied + 1);
});

test('scrolling over a panel zooms time on the main plot and frequency in the panel, about the pointer', () => {
  const s = load(LINED_UP);
  s.window.modalRangePanels.sync();
  const event = wheelAt(s, 0.5, 0.25, -120);
  assert.equal(event.prevented, true);
  // Time about 3 s on the main plot, which every panel follows; frequency about 35 Hz.
  assert.deepEqual(s.targets, ['main', 'panel']);
  near(s.relayouts[0]['xaxis.range'], [3 - STEP_IN, 3 + STEP_IN]);
  assert.equal(s.relayouts[0]['xaxis.autorange'], false);
  near(s.relayouts[1]['yaxis.range'], [35 - 30 * STEP_IN, 35 + 90 * STEP_IN]);
});

test('a panel zooms out no further than its band, and stays inside it', () => {
  const s = load(LINED_UP);
  s.window.modalRangePanels.sync();
  wheelAt(s, 0.5, 0.5, 120);
  // Already on the whole band: time zooms out on the main plot, the band stays.
  assert.deepEqual(s.targets, ['main']);
  assert.ok(s.relayouts.every(update => !('yaxis.range' in update)));
  // Zoomed in at the top of the band, zooming out moves the window down.
  s.panel._fullLayout.yaxis.range = [100, 125];
  wheelAt(s, 0.5, 0.8, 120);
  const range = s.relayouts.at(-1)['yaxis.range'];
  near([range[1]], [125]);
  near([range[1] - range[0]], [25 / STEP_IN]);
});

test('scrolling over a panel\'s axes or margins scrolls the page', () => {
  const s = load(LINED_UP);
  s.window.modalRangePanels.sync();
  assert.equal(wheelAt(s, -0.02, 0.5, -120).prevented, false);
  assert.equal(wheelAt(s, 0.5, 1.05, -120).prevented, false);
  assert.deepEqual(s.relayouts, []);
});

test('on a log axis a panel zooms in decades', () => {
  const band = [Math.log10(5), Math.log10(125)];
  const s = load({ ...LINED_UP, panelYRange: band.slice(), panelYType: 'log' });
  s.window.modalRangePanels.sync();
  wheelAt(s, 0.5, 0.5, -120);
  const middle = (band[0] + band[1]) / 2;
  const half = (band[1] - band[0]) / 2;
  near(s.relayouts.at(-1)['yaxis.range'], [middle - half * STEP_IN, middle + half * STEP_IN]);
});

test('a double-click on a panel resets the zoom, and a reset puts every panel back on its band', () => {
  const s = load(LINED_UP);
  s.window.modalRangePanels.sync();
  // Plotly's drag cover takes the native dblclick; its own clicks carry the count.
  s.panel.listeners.click({ detail: 1 });
  assert.deepEqual(s.relayouts, []);
  s.panel.listeners.click({ detail: 2 });
  assert.deepEqual(s.relayouts.at(-1), { 'xaxis.autorange': true, 'yaxis.autorange': true });
  assert.equal(s.targets.at(-1), 'main');
  s.panel._fullLayout.yaxis.range = [20, 60];
  s.window.modalRangePanels.resetBands();
  assert.deepEqual(s.relayouts.at(-1), { 'yaxis.range': [5, 125] });
  assert.equal(s.targets.at(-1), 'panel');
  s.panel._fullLayout.yaxis.range = [5, 125];
  const count = s.relayouts.length;
  s.window.modalRangePanels.resetBands();
  assert.equal(s.relayouts.length, count, 'already on its band');
});

test('a panel keeps its frequency zoom when Dash sends it again for the same clip and band', () => {
  const s = load(LINED_UP);
  s.panel.layout.uirevision = 'clip-1|low|5|125|linear';
  s.window.modalRangePanels.sync();
  wheelAt(s, 0.5, 0.25, -120);
  const zoomed = s.relayouts.at(-1)['yaxis.range'];
  // Re-created on the whole band (after a box is drawn): sync puts the zoom back.
  s.panel.layout = { meta: s.panel.layout.meta, uirevision: 'clip-1|low|5|125|linear' };
  s.panel._fullLayout.yaxis.range = [5, 125];
  s.window.modalRangePanels.sync();
  near(s.relayouts.at(-1)['yaxis.range'], zoomed);
  // Another clip starts on its whole band; so does every panel after a reset.
  s.panel._fullLayout.yaxis.range = [5, 125];
  s.panel.layout = { meta: s.panel.layout.meta, uirevision: 'clip-2|low|5|125|linear' };
  let count = s.relayouts.length;
  s.window.modalRangePanels.sync();
  assert.ok(s.relayouts.slice(count).every(update => !('yaxis.range' in update)));
  s.panel.layout = { meta: s.panel.layout.meta, uirevision: 'clip-1|low|5|125|linear' };
  s.window.modalRangePanels.resetBands();
  count = s.relayouts.length;
  s.window.modalRangePanels.sync();
  assert.ok(s.relayouts.slice(count).every(update => !('yaxis.range' in update)));
});
