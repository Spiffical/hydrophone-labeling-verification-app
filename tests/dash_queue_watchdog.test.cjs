const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

function setup(callbacks) {
    const dispatched = [];
    const store = { getState: () => ({ callbacks: store.callbacks }), dispatch: action => dispatched.push(action), callbacks };
    let tick = null;
    const window = { dash_stores: [store] };
    const setInterval = fn => { tick = fn; };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/dash_queue_watchdog.js`, 'utf8'), { window, setInterval });
    return { store, dispatched, tick: () => tick() };
}

const queue = overrides => ({
    requested: [], prioritized: [], blocked: [], executing: [], watched: [], executed: [], stored: [], completed: 0, ...overrides,
});

test('nudges a queue left waiting with nothing running', () => {
    const { dispatched, tick } = setup(queue({ requested: [{}] }));
    tick();
    assert.equal(dispatched.length, 0);
    tick();
    assert.equal(dispatched.length, 1);
    assert.equal(dispatched[0].type, 'Callbacks.Completed');
    assert.equal(dispatched[0].payload, 1);
});

test('leaves a queue alone while anything is running', () => {
    for (const name of ['prioritized', 'blocked', 'executing', 'watched', 'executed']) {
        const { dispatched, tick } = setup(queue({ requested: [{}], [name]: [{}] }));
        tick();
        tick();
        assert.equal(dispatched.length, 0, name);
    }
});

test('leaves a waiting list alone when it changed since the last check', () => {
    const { store, dispatched, tick } = setup(queue({ requested: [{}] }));
    tick();
    store.callbacks = queue({ requested: [{}] });
    tick();
    assert.equal(dispatched.length, 0);
});

test('does nothing on an empty queue or before Dash has started', () => {
    const { dispatched, tick } = setup(queue());
    tick();
    tick();
    assert.equal(dispatched.length, 0);
    const window = {};
    let early = null;
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/dash_queue_watchdog.js`, 'utf8'), { window, setInterval: fn => { early = fn; } });
    assert.doesNotThrow(() => early());
});
