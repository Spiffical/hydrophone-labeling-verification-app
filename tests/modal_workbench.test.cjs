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

// Clicks as the browser delivers them: the workbench's capture listener first, and
// the app sees a click (`handled`) only when that listener lets it through. Time,
// timers and Dash callback requests are fake.
function loadClicks() {
  let now = 1000;
  const timers = [];
  const listeners = [];
  const requests = [];
  class Element {}
  function dispatch(target) {
    const event = { target, preventDefault() {}, stopImmediatePropagation() { this.stopped = true; } };
    listeners.forEach(handler => { if (!event.stopped) handler(event); });
    if (!event.stopped) {
      target.handled.push(now);
      if (target.onHandled) target.onHandled();
    }
  }
  function control(id, selector) {
    return Object.assign(new Element(), {
      id, disabled: false, handled: [], getAttribute: () => null,
      closest(query) { return query.indexOf(selector) !== -1 ? this : null; },
      click() { dispatch(this); },
    });
  }
  const action = type => control(JSON.stringify({ scope: 'modal', type }), '#modal-item-actions');
  const accept = action('modal-verify-label-accept');
  const save = action('modal-action-confirm');
  const next = control('modal-nav-next', '#modal-nav-next');
  const saveNext = { disabled: false, classList: { toggle() {} } };
  const ids = { 'modal-nav-next': next, 'modal-save-next': saveNext };
  const window = {
    setTimeout: (fn, ms) => { timers.push({ at: now + ms, fn }); },
    localStorage: { getItem: () => null, setItem() {} },
    fetch: () => new Promise(resolve => { requests.push(resolve); }),
  };
  const document = {
    body: { classList: { toggle() {}, contains: () => false } },
    getElementById: id => ids[id] || null,
    querySelectorAll: selector => (selector.includes('modal-item-actions') ? [accept, save] : []),
    addEventListener(type, handler, capture) { if (type === 'click' && capture) listeners.push(handler); },
    documentElement: {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets/modal_workbench.js'), 'utf8'), {
    window, document, Element, Date: { now: () => now }, MutationObserver: class { observe() {} },
  });
  // A Dash callback request; call the returned function to answer it.
  const request = () => { window.fetch('/_dash-update-component'); return requests[requests.length - 1]; };
  const advance = async ms => {
    const end = now + ms;
    for (;;) {
      await new Promise(resolve => setImmediate(resolve));
      timers.sort((a, b) => a.at - b.at);
      if (!timers.length || timers[0].at > end) break;
      const timer = timers.shift();
      now = timer.at;
      timer.fn();
    }
    now = end;
  };
  return { workbench: window.modalWorkbench, accept, save, next, request, advance };
}

test('Save and an arrow made before the decision is in wait for it, then for the save, in order', async () => {
  // However the arrow's wait falls against the Save's.
  for (const gap of [0, 50, 100]) {
    const s = loadClicks();
    s.accept.click();
    const answerDecision = s.request();
    s.save.click();
    await s.advance(gap);
    s.next.click();
    await s.advance(2000);
    assert.deepEqual([s.save.handled.length, s.next.handled.length], [0, 0], 'held while the decision is on its way');

    let answerSave;
    s.save.onHandled = () => { answerSave = s.request(); };
    answerDecision();
    await s.advance(1000);
    assert.equal(s.save.handled.length, 1, `Save goes once the decision is in (gap ${gap} ms)`);
    assert.equal(s.next.handled.length, 0, `the arrow waits for the save (gap ${gap} ms)`);

    s.save.disabled = true; // the saved clip re-renders with Save disabled
    answerSave();
    await s.advance(1000);
    assert.equal(s.next.handled.length, 1);
    assert.ok(s.next.handled[0] > s.save.handled[0]);
  }
});

test('an arrow pressed during "Save and next" is dropped: it moves on once by itself', async () => {
  const s = loadClicks();
  s.accept.click();
  const answerDecision = s.request();
  s.workbench.saveAndNext();
  s.next.click();
  let answerSave;
  s.save.onHandled = () => { answerSave = s.request(); };
  answerDecision();
  await s.advance(1000);
  assert.equal(s.save.handled.length, 1);
  assert.equal(s.next.handled.length, 0);

  s.save.disabled = true;
  answerSave();
  await s.advance(1000);
  assert.equal(s.next.handled.length, 1);
});
