const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function load({ saveDisabled }) {
  const clicks = [];
  const save = {
    id: JSON.stringify({ scope: 'modal', type: 'modal-action-confirm' }),
    disabled: saveDisabled,
    click() { clicks.push('save'); },
  };
  const next = { disabled: false, getAttribute: () => null, click() { clicks.push('next'); } };
  const saveNext = { disabled: false, classList: { toggle() {} } };
  const ids = { 'modal-nav-next': next, 'modal-save-next': saveNext };
  const window = {
    setTimeout: (fn) => setTimeout(fn, 5),
    localStorage: { getItem: () => null, setItem() {} },
  };
  const document = {
    body: { classList: { toggle() {}, contains: () => false } },
    getElementById: id => ids[id] || null,
    querySelectorAll: selector => (selector.includes('modal-item-actions') ? [save] : []),
    addEventListener() {},
    documentElement: {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/modal_workbench.js'), 'utf8'), {
    window, document, MutationObserver: class { observe() {} },
  });
  return { workbench: window.modalWorkbench, save, saveNext, clicks };
}

test('save and next moves straight on when there is nothing to save', () => {
  const { workbench, clicks } = load({ saveDisabled: true });
  workbench.saveAndNext();
  assert.deepEqual(clicks, ['next']);
});

test('save and next waits for the save to finish before moving on', async () => {
  const { workbench, save, saveNext, clicks } = load({ saveDisabled: false });
  workbench.saveAndNext();
  assert.deepEqual(clicks, ['save']);
  assert.equal(saveNext.disabled, true, 'button blocked while saving');
  workbench.saveAndNext();
  assert.deepEqual(clicks, ['save'], 'no second save while the first is running');

  await new Promise(resolve => setTimeout(resolve, 30));
  assert.deepEqual(clicks, ['save'], 'still waiting while Save stays enabled');
  save.disabled = true; // the saved clip re-renders with Save disabled
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.deepEqual(clicks, ['save', 'next']);
  assert.equal(saveNext.disabled, false);
});
