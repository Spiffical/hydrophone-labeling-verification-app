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
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/modal_shortcuts.js`, 'utf8'), {
        window: { getComputedStyle: () => ({ visibility: 'visible' }) },
        document: { addEventListener: (_, h) => { handler = h; }, getElementById: id => ids[id],
            querySelectorAll: () => [wrapper, other] },
    });
    const press = (key, props = {}) => {
        const event = { key, target: { closest: () => null }, preventDefault() { this.prevented = true; }, ...props };
        handler(event); return event;
    };
    return { press, prev, next, edit, modal, other, busy };
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
