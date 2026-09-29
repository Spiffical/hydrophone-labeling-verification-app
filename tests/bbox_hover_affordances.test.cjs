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

// One box on the spectrogram with its × and ✎ handles, as Plotly renders them.
function load() {
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
  const shape = { getAttribute: () => '0', getBoundingClientRect: () => rect(150, 100, 50, 80) };
  const plot = {
    classList: classList(),
    layout: { shapes: [{ name: 'bbox-0' }] },
    data: [
      { name: '__bbox_delete_handle__', customdata: [0] },
      { name: '__bbox_edit_handle__', customdata: [0] },
    ],
    querySelector: () => null,
    querySelectorAll: selector => (selector.includes('shapelayer') ? [shape] : [del.trace, edit.trace]),
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
  return { hover: window.bboxHover, plot, del, fire, fireDocument };
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

test('only a shown ✎ takes clicks; the × leaves them to Plotly', () => {
  const css = fs.readFileSync(path.join(__dirname, '../app/assets/bbox_panel.css'), 'utf8');
  const rules = css.split('}').filter(rule => rule.includes('modal-bbox-handle-trace') && /pointer-events:\s*auto/.test(rule));
  assert.ok(rules.length > 0);
  for (const rule of rules) {
    const selectors = rule.slice(0, rule.indexOf('{')).split(',').map(selector => selector.trim()).filter(Boolean);
    assert.ok(selectors.every(selector => selector.includes('modal-bbox-handle-trace--edit')), selectors.join(', '));
  }
});
