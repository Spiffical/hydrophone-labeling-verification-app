const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// A main spectrogram with a colour bar (plot area 101-946 px on the page) and
// one other range under it, as the modal lays them out.
function plot({ left, width, size, range }) {
  const handlers = {};
  return {
    _fullLayout: { _size: size, xaxis: { range } },
    getBoundingClientRect: () => ({ left, right: left + width, width }),
    on(name, handler) { handlers[name] = handler; },
    handlers,
  };
}

function load({ panelLeft = 44, panelWidth = 1006, panelSize = { l: 70, r: 36, w: 900 }, panelRange = [0, 9.75] } = {}) {
  const main = plot({ left: 44, width: 1006, size: { l: 57, r: 104, w: 845 }, range: [2, 4] });
  const panel = plot({ left: panelLeft, width: panelWidth, size: panelSize, range: panelRange });
  const relayouts = [];
  const window = {
    requestAnimationFrame: callback => { callback(); return 1; },
    Plotly: {
      relayout(gd, update) {
        relayouts.push(JSON.parse(JSON.stringify(update)));
        return Promise.resolve();
      },
    },
  };
  const document = {
    documentElement: {},
    querySelector: selector => (selector.includes('modal-image-graph') ? main : null),
    querySelectorAll: selector => (selector.includes('spectrogram-modal-range-graph') ? [panel] : []),
  };
  class MutationObserver { observe() {} }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/modal_range_panels.js'), 'utf8'), {
    window, document, MutationObserver,
  });
  return { window, main, panel, relayouts };
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
