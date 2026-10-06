const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// The main spectrogram (plot area 101-946 px across, 112-400 px down) and the
// detector score strip under it, as the server sends it: its own margins and
// the whole clip.
function plot({ left, width, size, range, yRange }) {
  const handlers = {};
  const gd = {
    layout: { meta: {} },
    _fullLayout: { _size: size, xaxis: { range }, yaxis: { type: 'linear', range: yRange }, dragmode: false },
    getBoundingClientRect: () => ({ left, right: left + width, width, top: 100 }),
    on(name, handler) { handlers[name] = handler; },
    addEventListener() {},
    handlers,
  };
  return gd;
}

function load() {
  const main = plot({ left: 44, width: 1006, size: { l: 57, r: 104, w: 845, t: 12, h: 288 }, range: [2, 4], yRange: [5, 100] });
  main.layout.meta = { x_min: 0, x_max: 10, display_y_min_hz: 5, display_y_max_hz: 100 };
  const strip = plot({ left: 44, width: 1006, size: { l: 70, r: 36, w: 900, t: 4, h: 56 }, range: [0, 10], yRange: [0, 1.04] });
  const relayouts = [];
  const window = {
    requestAnimationFrame: callback => { callback(); return null; },
    Plotly: {
      relayout(gd, update) {
        relayouts.push({ target: gd === main ? 'main' : 'strip', update: JSON.parse(JSON.stringify(update)) });
        if (update['xaxis.range']) gd._fullLayout.xaxis.range = update['xaxis.range'];
        if (update['yaxis.range']) gd._fullLayout.yaxis.range = update['yaxis.range'];
        return Promise.resolve();
      },
    },
  };
  const documentListeners = {};
  const document = {
    documentElement: {},
    getElementById: () => null,
    querySelector: selector => {
      if (selector.includes('modal-score-track-graph')) return strip;
      if (selector.includes('modal-image-graph')) return main;
      return null;
    },
    querySelectorAll: () => [],
    addEventListener: (name, handler) => { documentListeners[name] = handler; },
  };
  class MutationObserver { observe() {} }
  for (const file of ['modal_range_panels.js', 'modal_scroll_zoom.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets', file), 'utf8'), {
      window, document, MutationObserver,
    });
  }
  return { window, main, strip, relayouts, documentListeners };
}

test('the score strip takes the main plot\'s plot-area edges and time window', () => {
  const { window, relayouts } = load();
  window.modalRangePanels.sync();
  assert.deepEqual(relayouts, [{ target: 'strip', update: { 'margin.l': 57, 'margin.r': 104, 'xaxis.range': [2, 4] } }]);
});

test('the strip follows the main plot as it zooms, and realigns a figure from the server', () => {
  const { window, main, strip, relayouts } = load();
  window.modalRangePanels.sync();
  strip._fullLayout._size = { l: 57, r: 104, w: 845, t: 4, h: 56 };
  main._fullLayout.xaxis.range = [2.5, 3.5];
  main.handlers.plotly_relayout();
  assert.deepEqual(relayouts[1], { target: 'strip', update: { 'xaxis.range': [2.5, 3.5] } });
  // A new strip figure for the next clip comes with the whole clip again.
  strip._fullLayout.xaxis.range = [0, 10];
  strip.handlers.plotly_afterplot();
  assert.deepEqual(relayouts[2], { target: 'strip', update: { 'xaxis.range': [2.5, 3.5] } });
});

test('scrolling over the strip zooms time on the main plot and nothing else', () => {
  const s = load();
  const event = {
    target: { closest: selector => (selector.includes('modal-score-track-graph') ? s.strip : null) },
    // Halfway across the strip's plot area once lined up with the main plot.
    clientX: 101 + 845 * 0.5, clientY: 100 + 4 + 28, deltaY: -100,
    prevented: false, preventDefault() { this.prevented = true; },
  };
  s.strip._fullLayout._size = { l: 57, r: 104, w: 845, t: 4, h: 56 };
  s.documentListeners.wheel(event);
  assert.equal(event.prevented, true);
  const mainUpdates = s.relayouts.filter(entry => entry.target === 'main');
  assert.equal(mainUpdates.length, 1);
  assert.deepEqual(Object.keys(mainUpdates[0].update).sort(), ['xaxis.autorange', 'xaxis.range']);
  const range = mainUpdates[0].update['xaxis.range'];
  const step = Math.exp(-0.1);
  assert.ok(Math.abs(range[0] - (3 - step)) < 1e-9 && Math.abs(range[1] - (3 + step)) < 1e-9, JSON.stringify(range));
  assert.ok(!s.relayouts.some(entry => entry.target === 'strip' && entry.update['yaxis.range']));
});
