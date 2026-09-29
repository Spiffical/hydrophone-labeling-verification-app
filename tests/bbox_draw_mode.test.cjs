const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// A sidebar with a + button per label, as the modal renders them.
function load({ labels = ['Bio > Fin whale', 'Bio > Blue whale'], editable = true } = {}) {
  const calls = [];
  const buttons = labels.map(label => ({
    id: JSON.stringify({ label, type: 'modal-label-add-box' }),
    disabled: false,
    clicks: 0,
    click() { this.clicks += 1; },
  }));
  const panel = { querySelectorAll: () => buttons };
  const window = {
    bboxPanel: { canEdit: () => editable },
    dash_clientside: {
      set_props: (id, props) => calls.push([id, props]),
      bboxInteractions: { setPanMode: () => calls.push(['pan']) },
    },
    setTimeout,
    clearTimeout,
  };
  const document = {
    getElementById: id => (id === 'modal-item-actions' ? panel : null),
    querySelector: () => null,
    addEventListener() {},
    documentElement: {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/bbox_draw_mode.js'), 'utf8'), {
    window, document, MutationObserver: class { observe() {} },
  });
  return { draw: window.bboxDrawMode, state: window.bboxDraw, buttons, calls };
}

test('draw mode arms the chosen label through its + button and stays on', () => {
  const { draw, state, buttons } = load();
  assert.deepEqual(Array.from(draw.labels()), ['Bio > Fin whale', 'Bio > Blue whale']);
  assert.equal(draw.enable(), true);
  assert.equal(state.sticky, true);
  assert.equal(buttons[0].clicks, 1, 'first label by default');

  draw.setLabel('Bio > Blue whale');
  assert.equal(buttons[1].clicks, 1, 'switching label re-arms for it');
  assert.equal(draw.label(), 'Bio > Blue whale');
});

test('turning draw mode off clears the active label and returns to pan', () => {
  const { draw, calls } = load();
  let notified = 0;
  draw.subscribe(() => { notified += 1; });
  draw.enable();
  assert.equal(draw.toggle(), false);
  assert.equal(draw.isOn(), false);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['modal-active-box-label', { data: null }], ['pan']]);
  assert.equal(notified, 2);
});

test('draw mode needs an editable clip with at least one label', () => {
  assert.equal(load({ editable: false }).draw.enable(), false);
  const noLabels = load({ labels: [] });
  assert.equal(noLabels.draw.enable(), false);
  assert.equal(noLabels.state.sticky, false);
});
