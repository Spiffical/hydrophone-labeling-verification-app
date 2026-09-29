const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// The plot column: a panel above the main plot, a splitter, then the main plot.
function load({ stored = null } = {}) {
  const listeners = {};
  let saved = stored;
  function panel(key, height, grow, minHeight, order) {
    const classes = new Set();
    const button = {
      attributes: {},
      title: '',
      setAttribute(name, value) { this.attributes[name] = value; },
      querySelector: () => ({ className: '' }),
      closest: selector => (selector.includes('minimize') ? button : selector.includes('data-range-key') ? node : null),
    };
    const node = {
      order, grow, minHeight, style: {},
      getAttribute: name => (name === 'data-range-key' ? key : null),
      getBoundingClientRect: () => ({ height }),
      classList: {
        toggle: (name, on) => { if (on) classes.add(name); else classes.delete(name); },
        contains: name => classes.has(name),
      },
      querySelector: () => button,
      compareDocumentPosition: other => (other.order > order ? 4 : 2),
      button,
    };
    return node;
  }
  const high = panel('high', 200, 2, 120, 0);
  const splitter = { order: 1 };
  const main = panel('main', 300, 3, 200, 2);
  const column = { querySelectorAll: () => [high, main], classList: { add() {}, remove() {} } };
  const window = {
    localStorage: { getItem: () => saved, setItem: (_key, value) => { saved = value; } },
    getComputedStyle: node => ({ flexGrow: String(node.style.flexGrow || node.grow), minHeight: node.minHeight + 'px' }),
    requestAnimationFrame: callback => { callback(); return null; },
  };
  const document = {
    documentElement: {},
    addEventListener: (type, handler) => { (listeners[type] = listeners[type] || []).push(handler); },
    querySelector: selector => (selector === '.modal-workbench-plot' ? column : null),
    getElementById: () => null,
  };
  class MutationObserver { observe() {} }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/modal_range_layout.js'), 'utf8'),
    { window, document, MutationObserver, Node: { DOCUMENT_POSITION_FOLLOWING: 4 } });
  return { window, high, main, splitter, listeners, saved: () => JSON.parse(saved) };
}

test('dragging a splitter gives one neighbour the height the other loses', () => {
  const s = load();
  const layout = s.window.modalRangeLayout;
  const resize = layout.beginResize(s.splitter);
  layout.resizeBy(resize, 50); // 200/300 px -> 250/250 px of the pair's 5 grow
  assert.deepEqual({ ...layout.state.sizes }, { high: 2.5, main: 2.5 });
  assert.equal(s.high.style.flexGrow, '2.5');
  // Neither goes below its minimum height (200 px for the main plot).
  layout.resizeBy(resize, 1000);
  assert.deepEqual({ ...layout.state.sizes }, { high: 3, main: 2 });
  layout.resizeBy(resize, -1000);
  assert.deepEqual({ ...layout.state.sizes }, { high: 1.2, main: 3.8 });
});

test('a minimized panel keeps its header and is remembered in this browser', () => {
  const s = load();
  s.listeners.click.forEach(handler => handler({ target: { closest: selector => s.high.button.closest(selector) } }));
  assert.equal(s.high.classList.contains('is-minimized'), true);
  assert.equal(s.high.button.attributes['aria-expanded'], 'false');
  assert.deepEqual({ ...s.saved().minimized }, { high: true });

  // A fresh page restores it.
  const again = load({ stored: JSON.stringify(s.saved()) });
  again.window.modalRangeLayout.apply();
  assert.equal(again.high.classList.contains('is-minimized'), true);
});
