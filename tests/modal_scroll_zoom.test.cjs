const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// The modal's main spectrogram: a 52.6 s clip shown 5-100 Hz, plot area
// 101-946 px across and 112-400 px down the page.
function load({ xRange = [0, 52.6], yRange = [5, 100] } = {}) {
  const main = {
    layout: { meta: { x_min: 0, x_max: 52.6, y_to_hz: 1, display_y_min_hz: 5, display_y_max_hz: 100 } },
    _fullLayout: { _size: { l: 57, r: 104, t: 12, w: 845, h: 288 }, xaxis: { range: xRange.slice() }, yaxis: { type: 'linear', range: yRange.slice() } },
    getBoundingClientRect: () => ({ left: 44, top: 100, width: 1006 }),
  };
  const relayouts = [];
  const frames = [];
  const listeners = {};
  const window = {
    requestAnimationFrame: callback => { frames.push(callback); return frames.length; },
    Plotly: {
      relayout(gd, update) {
        relayouts.push(JSON.parse(JSON.stringify(update)));
        if (update['xaxis.range']) gd._fullLayout.xaxis.range = update['xaxis.range'].slice();
        if (update['yaxis.range']) gd._fullLayout.yaxis.range = update['yaxis.range'].slice();
        return Promise.resolve();
      },
    },
  };
  const document = {
    querySelector: selector => (selector.includes('modal-image-graph') ? main : null),
    addEventListener: (name, handler, options) => { listeners[name] = { handler, options }; },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/modal_scroll_zoom.js'), 'utf8'), { window, document });
  const wheel = (across, up, deltaY) => {
    const event = {
      target: { closest: selector => (selector.includes('modal-image-graph') ? main : null) },
      clientX: 101 + 845 * across, clientY: 400 - 288 * up, deltaY,
      prevented: false, preventDefault() { this.prevented = true; },
    };
    listeners.wheel.handler(event);
    return event;
  };
  const frame = () => { while (frames.length) frames.shift()(); };
  return { main, relayouts, listeners, wheel, frame };
}

const STEP = Math.exp(0.1); // Plotly's largest step, one wheel notch
const near = (actual, expected) => assert.ok(
  actual.length === expected.length && actual.every((value, index) => Math.abs(value - expected[index]) < 1e-9),
  JSON.stringify(actual) + ' vs ' + JSON.stringify(expected));

test('the app, not Plotly, takes wheel events, before Plotly sees them', () => {
  const s = load();
  assert.deepEqual(JSON.parse(JSON.stringify(s.listeners.wheel.options)), { capture: true, passive: false });
});

test('scrolling over the main plot zooms time and frequency about the pointer, once per frame', () => {
  const s = load();
  // Two notches in at 13.15 s and 28.75 Hz, in one frame: one relayout.
  assert.equal(s.wheel(0.25, 0.25, -120).prevented, true);
  s.wheel(0.25, 0.25, -120);
  assert.equal(s.relayouts.length, 0, 'applied on the next frame');
  s.frame();
  assert.equal(s.relayouts.length, 1);
  const factor = 1 / (STEP * STEP);
  near(s.relayouts[0]['xaxis.range'], [13.15 - 13.15 * factor, 13.15 + 39.45 * factor]);
  near(s.relayouts[0]['yaxis.range'], [28.75 - 23.75 * factor, 28.75 + 71.25 * factor]);
  assert.equal(s.relayouts[0]['xaxis.autorange'], false);
});

test('zooming out stops at the whole clip and the plot\'s band, not in empty space', () => {
  const s = load({ xRange: [40, 50], yRange: [80, 95] });
  for (let i = 0; i < 30; i += 1) s.wheel(0.9, 0.9, 120);
  s.frame();
  near(s.relayouts.at(-1)['xaxis.range'], [0, 52.6]);
  near(s.relayouts.at(-1)['yaxis.range'], [5, 100]);
  // Further out changes nothing, so nothing is redrawn.
  const count = s.relayouts.length;
  s.wheel(0.5, 0.5, 120);
  s.frame();
  assert.equal(s.relayouts.length, count);
  // Partly out, near the end: the view slides back inside the clip.
  const t = load({ xRange: [45, 52.6] });
  t.wheel(0.9, 0.5, 120);
  t.frame();
  const range = t.relayouts.at(-1)['xaxis.range'];
  near([range[1]], [52.6]);
  near([range[1] - range[0]], [7.6 * STEP]);
});

test('over the axes, colour bar or margins the page scrolls', () => {
  const s = load();
  assert.equal(s.wheel(-0.03, 0.5, -120).prevented, false);
  assert.equal(s.wheel(1.08, 0.5, -120).prevented, false);
  assert.equal(s.wheel(0.5, -0.1, -120).prevented, false);
  s.frame();
  assert.deepEqual(s.relayouts, []);
});

// A press, drag and release on the main plot's axes (plot area 101-946 px
// across, 112-400 px down; the time axis labels run below 400 px).
function press(s, x, y, plotlyArea = null) {
  const event = {
    button: 0, clientX: x, clientY: y,
    target: { closest: selector => (selector.includes('modal-image-graph') ? s.main : (plotlyArea && selector.includes(plotlyArea) ? {} : null)) },
    prevented: false, stopped: false,
    preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; },
  };
  s.listeners.mousedown.handler(event);
  return event;
}
const moveTo = (s, x, y) => s.listeners.mousemove.handler({ clientX: x, clientY: y, preventDefault() {} });
const release = s => s.listeners.mouseup.handler({});

test('dragging the time axis zooms it about the point pressed instead of panning', () => {
  const s = load();
  // Pressed at 13.15 s on Plotly's axis drag area: Plotly never sees it.
  const down = press(s, 101 + 845 * 0.25, 410, '.ewdrag');
  assert.equal(down.stopped, true);
  moveTo(s, 101 + 845 * 0.25 + 150, 410);
  s.frame();
  near(s.relayouts.at(-1)['xaxis.range'], [13.15 - 13.15 * Math.exp(-1), 13.15 + 39.45 * Math.exp(-1)]);
  assert.equal('yaxis.range' in s.relayouts.at(-1), false);
  // Back to where it started: back to the view it started from.
  moveTo(s, 101 + 845 * 0.25, 410);
  s.frame();
  near(s.relayouts.at(-1)['xaxis.range'], [0, 52.6]);
  release(s);
  // Dragging left zooms out, no further than the whole clip.
  press(s, 500, 415);
  moveTo(s, 100, 415);
  s.frame();
  near(s.relayouts.at(-1)['xaxis.range'], [0, 52.6]);
  release(s);
});

test('dragging the frequency axis up zooms it in about the point pressed', () => {
  const s = load();
  press(s, 80, 400 - 288 * 0.5); // the tick labels left of the plot, at 52.5 Hz
  moveTo(s, 80, 400 - 288 * 0.5 - 150);
  s.frame();
  near(s.relayouts.at(-1)['yaxis.range'], [52.5 - 47.5 * Math.exp(-1), 52.5 + 47.5 * Math.exp(-1)]);
  release(s);
  moveTo(s, 80, 0);
  s.frame();
  assert.equal(s.relayouts.length, 1, 'released: moving no longer zooms');
});

test('presses inside the plot are left to Plotly, and a double-click on an axis resets it', () => {
  const s = load({ xRange: [10, 20], yRange: [40, 60] });
  const inside = press(s, 500, 250);
  assert.equal(inside.prevented, false);
  moveTo(s, 700, 250);
  s.frame();
  assert.deepEqual(s.relayouts, []);
  const dbl = (x, y) => s.listeners.dblclick.handler({
    clientX: x, clientY: y, target: { closest: selector => (selector.includes('modal-image-graph') ? s.main : null) },
    preventDefault() {}, stopPropagation() {},
  });
  dbl(500, 415);
  near(s.relayouts.at(-1)['xaxis.range'], [0, 52.6]);
  dbl(80, 250);
  near(s.relayouts.at(-1)['yaxis.range'], [5, 100]);
});
