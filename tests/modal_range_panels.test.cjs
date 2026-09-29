const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// A main spectrogram with a colour bar (plot area 101-946 px on the page) and
// one other range under it, as the modal lays them out.
function plot({ left, width, size, range, meta = {} }) {
  const handlers = {};
  const gd = {
    layout: { meta },
    _fullLayout: { _size: size, xaxis: { range }, yaxis: { type: 'linear' }, dragmode: false },
    // Already showing the clip's (no) boxes.
    _rangePanelShapes: '[]',
    _rangePanelLayout: null,
    getBoundingClientRect: () => ({ left, right: left + width, width }),
    on(name, handler) { handlers[name] = handler; },
    handlers,
  };
  gd._rangePanelLayout = gd.layout;
  return gd;
}

function load({ panelLeft = 44, panelWidth = 1006, panelSize = { l: 70, r: 36, w: 900 }, panelRange = [0, 9.75],
  boxes = [], drawing = false } = {}) {
  const main = plot({ left: 44, width: 1006, size: { l: 57, r: 104, w: 845 }, range: [2, 4] });
  // The Low range (5-125 Hz) of a 10 s clip.
  const panel = plot({ left: panelLeft, width: panelWidth, size: panelSize, range: panelRange,
    meta: { range_id: 'low', freq_min_hz: 5, freq_max_hz: 125, x_min: 0, x_max: 10, x_to_seconds: 1 } });
  const relayouts = [];
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
        return Promise.resolve();
      },
    },
  };
  const document = {
    documentElement: {},
    getElementById: () => null,
    querySelector: selector => (selector.includes('modal-image-graph') ? main : null),
    querySelectorAll: selector => (selector.includes('spectrogram-modal-range-graph') ? [panel] : []),
  };
  class MutationObserver { observe() {} }
  for (const file of ['bbox_clientside.js', 'modal_range_panels.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets', file), 'utf8'), {
      window, document, MutationObserver,
    });
  }
  return { window, main, panel, relayouts, added, setDrawing: on => { drawing = on; }, drawSubscriber: () => drawSubscriber };
}

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
