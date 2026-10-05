const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function classList() {
  const names = new Set();
  return {
    toggle(name, force) {
      const on = force === undefined ? !names.has(name) : Boolean(force);
      if (on) names.add(name); else names.delete(name);
      return on;
    },
    contains: name => names.has(name),
    add: name => names.add(name),
    remove: name => names.delete(name),
  };
}

function rect(left, top, width, height) {
  return { left, top, right: left + width, bottom: top + height, width, height };
}

// One box on the spectrogram with its × and ✎ handles, as Plotly renders them;
// with `reference`, also the expert's box around it (ref-box-0).
function load({ reference = false } = {}) {
  const handle = (glyph, bounds) => {
    const point = { classList: classList(), getBoundingClientRect: () => bounds };
    const text = { classList: classList(), getBoundingClientRect: () => bounds };
    return {
      point,
      trace: {
        classList: classList(),
        querySelector: selector => (selector === 'text' ? { textContent: glyph } : null),
        querySelectorAll: selector => (selector === '.points .point' ? [point] : [text]),
      },
    };
  };
  const del = handle('×', rect(212, 88, 10, 10));
  const edit = handle('✎', rect(212, 130, 10, 10));
  const shape = { getAttribute: () => '0', getBoundingClientRect: () => rect(150, 100, 50, 80), style: {} };
  const outline = { getAttribute: () => '1', getBoundingClientRect: () => rect(120, 90, 120, 110), style: {} };
  const plot = {
    classList: classList(),
    layout: { shapes: reference ? [{ name: 'bbox-0' }, { name: 'ref-box-0' }] : [{ name: 'bbox-0' }] },
    data: [
      { name: '__bbox_delete_handle__', customdata: [0] },
      { name: '__bbox_edit_handle__', customdata: [0] },
    ],
    querySelector: () => null,
    querySelectorAll: selector => (selector.includes('shapelayer') ? (reference ? [shape, outline] : [shape]) : [del.trace, edit.trace]),
  };
  const graphListeners = {};
  const documentListeners = {};
  const graph = {
    dataset: {},
    querySelector: () => plot,
    getBoundingClientRect: () => rect(0, 0, 600, 400),
    addEventListener: (type, listener) => { (graphListeners[type] = graphListeners[type] || []).push(listener); },
  };
  const window = { innerWidth: 1440, innerHeight: 900 };
  const document = {
    readyState: 'complete',
    documentElement: {},
    getElementById: id => (id === 'modal-image-graph' ? graph : null),
    addEventListener: (type, listener, options) => {
      (documentListeners[type] = documentListeners[type] || []).push({ listener, once: options && options.once });
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/bbox_hover_affordances.js'), 'utf8'), {
    window, document, MutationObserver: class { observe() {} },
  });
  const fire = (type, event) => (graphListeners[type] || []).forEach(listener => listener(event));
  const fireDocument = (type, event) => {
    const listeners = documentListeners[type] || [];
    documentListeners[type] = listeners.filter(entry => !entry.once);
    listeners.forEach(entry => entry.listener(event));
  };
  return { hover: window.bboxHover, window, plot, shape, outline, del, fire, fireDocument };
}

test('hovering a box shows its handles and a pointer over its ×', () => {
  const s = load();
  s.fire('mousemove', { clientX: 170, clientY: 140, buttons: 0 });
  assert.equal(s.hover.activeBox, 0);
  assert.equal(s.del.point.classList.contains('is-visible'), true);
  s.fire('mousemove', { clientX: 217, clientY: 93, buttons: 0 });
  assert.equal(s.hover.activeBox, 0, 'moving onto the × keeps the box');
  assert.equal(s.plot.classList.contains('modal-bbox-over-delete'), true);
});

test('pressing the × keeps its box hovered so the click can delete it', () => {
  const s = load();
  s.fire('mousemove', { clientX: 217, clientY: 93, buttons: 0 });
  s.fire('mousemove', { clientX: 170, clientY: 140, buttons: 0 });
  s.fire('mousemove', { clientX: 217, clientY: 93, buttons: 0 });
  // Plotly's drag cover makes the graph fire mouseleave while the button is down,
  // and a real click often moves the pointer a pixel.
  s.fire('mouseleave', { clientX: 217, clientY: 93, buttons: 1 });
  s.fire('mousemove', { clientX: 218, clientY: 93, buttons: 1 });
  assert.equal(s.hover.activeBox, 0);
  s.fireDocument('mouseup', { clientX: 218, clientY: 93 });
  assert.equal(s.hover.activeBox, 0, 'released on the plot');
  s.fire('mouseleave', { clientX: 700, clientY: 93, buttons: 0 });
  assert.equal(s.hover.activeBox, null, 'a plain mouseleave clears it');
});

test('releasing a press off the plot clears the hovered box', () => {
  const s = load();
  s.fire('mousemove', { clientX: 170, clientY: 140, buttons: 0 });
  s.fire('mouseleave', { clientX: 170, clientY: 140, buttons: 1 });
  s.fireDocument('mouseup', { clientX: 900, clientY: 700 });
  assert.equal(s.hover.activeBox, null);
});

test('the expert outlines let the pointer through; boxes stay draggable', () => {
  // Shape editing makes every shape draggable; a drag starting inside an
  // outline must pan or draw instead of moving the outline.
  const s = load({ reference: true });
  assert.equal(s.outline.style.pointerEvents, 'none');
  assert.equal(s.shape.style.pointerEvents, undefined);
  s.fire('mousemove', { clientX: 130, clientY: 95, buttons: 0 });
  assert.equal(s.hover.activeBox, null, 'inside the outline only, no box is hovered');
  s.fire('mousemove', { clientX: 170, clientY: 140, buttons: 0 });
  assert.equal(s.hover.activeBox, 0);
});

test('scrolling over a box zooms like scrolling over the plot', () => {
  // Plotly zooms on wheel events at its drag layer; boxes are drawn above it.
  const s = load();
  const sent = [];
  const area = { getBoundingClientRect: () => rect(0, 0, 600, 400), dispatchEvent: event => sent.push(event) };
  s.plot.querySelector = selector => (selector === '.nsewdrag' ? area : null);
  s.window.WheelEvent = class { constructor(type, init) { Object.assign(this, init, { type }); } };
  const wheel = (inBox) => {
    const event = {
      target: { closest: selector => (inBox && selector === '.shapelayer' ? {} : null) },
      clientX: 170, clientY: 140, deltaX: 0, deltaY: -120, deltaMode: 0,
      prevented: false, preventDefault() { this.prevented = true; }, stopPropagation() {},
    };
    s.fire('wheel', event);
    return event;
  };

  assert.equal(wheel(true).prevented, true);
  assert.equal(sent.length, 1);
  assert.deepEqual([sent[0].type, sent[0].clientX, sent[0].clientY, sent[0].deltaY, sent[0].bubbles], ['wheel', 170, 140, -120, true]);
  assert.equal(wheel(false).prevented, false, 'elsewhere Plotly gets the wheel itself');
  assert.equal(sent.length, 1);
});

test('only a shown ✎ takes clicks; the × leaves them to Plotly', () => {
  const css = fs.readFileSync(path.join(__dirname, '../app/assets/bbox_panel.css'), 'utf8');
  const rules = css.split('}').filter(rule => rule.includes('modal-bbox-handle-trace') && /pointer-events:\s*auto/.test(rule));
  assert.ok(rules.length > 0);
  for (const rule of rules) {
    const selectors = rule.slice(0, rule.indexOf('{')).split(',').map(selector => selector.trim()).filter(Boolean);
    assert.ok(selectors.every(selector => selector.includes('modal-bbox-handle-trace--edit')), selectors.join(', '));
  }
});
