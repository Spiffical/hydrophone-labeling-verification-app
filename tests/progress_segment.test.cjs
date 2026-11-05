const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

function setup(...changed) {
    const dc = { no_update: {}, callback_context: { triggered: changed.map(id => ({ prop_id: `${id}.value` })) } };
    const window = { dash_clientside: dc };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/progress_segment.js`, 'utf8'), { window });
    return { noUpdate: dc.no_update, release: window.dash_clientside.progressSegment.release };
}

const segment = { bin: 4, category: 'Biophony', state: 'verified', range: [40, 50] };
const view = { order: 'precision', segment };
const release = (changed, range, status, currentView = view) => {
    const { noUpdate, release: run } = setup(...changed);
    const result = run(range, status, null, true, '2026-10-05', 'ICLISTENHF6324', currentView);
    return result === noUpdate ? 'kept' : result;
};

test('keeps a segment while the range and status are the ones it set', () => {
    assert.equal(release(['verify-threshold-slider', 'verify-status-filter'], [40, 50], 'verified'), 'kept');
});

test('lets go of a segment when the range or status moves away from it', () => {
    const moved = release(['verify-threshold-slider'], [30, 50], 'verified');
    assert.equal(moved.segment, null);
    assert.equal(moved.order, 'precision');
    assert.equal(release(['verify-status-filter'], [40, 50], 'all').segment, null);
});

test('lets go of a segment when the classes, chart scope, date or device change', () => {
    for (const id of ['verify-class-filter', 'verify-progress-all-categories', 'global-date-selector', 'global-device-selector']) {
        assert.equal(release([id], [40, 50], 'verified').segment, null, id);
    }
});

test('does nothing without a segment', () => {
    assert.equal(release(['verify-status-filter'], [30, 50], 'all', { order: 'precision', segment: null }), 'kept');
    assert.equal(release(['verify-status-filter'], [30, 50], 'all', null), 'kept');
});
