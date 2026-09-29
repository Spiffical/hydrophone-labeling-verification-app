const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

function setup() {
    let handler;
    const element = () => ({ clicks: 0, getClientRects() { return this.hidden ? [] : [{}]; },
        getAttribute() { return null; }, contains() { return false; }, click() { this.clicks++; } });
    const prev = element(), next = element(), edit = element(), modal = element(), other = element(), busy = element();
    const wrapper = element();
    wrapper.contains = e => e === modal;
    other.hidden = busy.hidden = true;
    modal.querySelector = () => edit;
    const ids = { 'image-modal': modal, 'modal-busy-overlay': busy, 'modal-nav-prev': prev, 'modal-nav-next': next };
    const win = { getComputedStyle: () => ({ visibility: 'visible' }) };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/modal_shortcuts.js`, 'utf8'), {
        window: win,
        document: { addEventListener: (_, h) => { handler = h; }, getElementById: id => ids[id],
            querySelectorAll: () => [wrapper, other] },
    });
    const press = (key, props = {}) => {
        const event = { key, target: { closest: () => null }, preventDefault() { this.prevented = true; }, ...props };
        handler(event); return event;
    };
    return { press, prev, next, edit, modal, other, busy, win };
}

test('arrows and E invoke existing modal buttons', () => {
    const s = setup();
    assert.equal(s.press('ArrowRight').prevented, true);
    s.press('ArrowLeft'); s.press('e');
    assert.deepEqual([s.prev.clicks, s.next.clicks, s.edit.clicks], [1, 1, 1]);
});

test('typing, sliders, modifiers, repeats, composition and other dialogs keep keyboard ownership', () => {
    const s = setup();
    for (const props of [{ target: { closest: () => ({}) } }, { repeat: true }, { ctrlKey: true },
        { metaKey: true }, { altKey: true }, { shiftKey: true }, { isComposing: true }, { defaultPrevented: true }]) {
        assert.equal(s.press('ArrowRight', props).prevented, undefined);
    }
    s.other.hidden = false; s.press('ArrowRight'); s.other.hidden = true;
    s.busy.hidden = false; s.press('ArrowRight'); s.busy.hidden = true;
    s.modal.hidden = true; s.press('ArrowRight'); s.modal.hidden = false;
    s.next.disabled = true; s.press('ArrowRight');
    assert.equal(s.next.clicks, 0);
});

test('number keys go to the box tag shortcuts and are consumed only when handled', () => {
    const s = setup();
    const keys = [];
    s.win.bboxPanel = { handleTagKey: key => { keys.push(key); return key !== '9'; } };
    assert.equal(s.press('3').prevented, true);
    assert.equal(s.press('9').prevented, undefined);
    // Typing in a field keeps its digits.
    assert.equal(s.press('2', { target: { closest: () => ({}) } }).prevented, undefined);
    assert.deepEqual(keys, ['3', '9']);
    assert.deepEqual([s.prev.clicks, s.next.clicks, s.edit.clicks], [0, 0, 0]);
});

test('B toggles draw mode, Esc stops it, and Enter saves and moves on', () => {
    const s = setup();
    const actions = [];
    let on = false;
    s.win.bboxDrawMode = { isOn: () => on, toggle() { on = !on; actions.push('toggle'); }, disable() { on = false; actions.push('off'); } };
    s.win.modalWorkbench = { saveAndNext() { actions.push('save-next'); } };
    assert.equal(s.press('Escape').prevented, undefined, 'Esc is left alone when not drawing');
    assert.equal(s.press('b').prevented, true);
    assert.equal(s.press('Escape').prevented, true);
    assert.equal(s.press('Enter').prevented, true);
    // A focused button keeps Enter for itself.
    const onButton = s.press('Enter', { target: { closest: selector => (selector.includes('button') ? {} : null) } });
    assert.equal(onButton.prevented, undefined);
    assert.deepEqual(actions, ['toggle', 'off', 'save-next']);
});

test('[ and ] (or Page Up/Down) turn the pages of a long clip', () => {
    const s = setup();
    const steps = [];
    s.win.modalPaging = { step(delta) { steps.push(delta); return true; } };
    assert.equal(s.press(']').prevented, true);
    assert.equal(s.press('[').prevented, true);
    assert.equal(s.press('PageDown').prevented, true);
    assert.equal(s.press('PageUp').prevented, true);
    assert.deepEqual(steps, [1, -1, 1, -1]);
    // A clip that fits on one page leaves the keys alone.
    s.win.modalPaging = { step() { return false; } };
    assert.equal(s.press(']').prevented, undefined);
});
