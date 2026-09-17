const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
function setup() {
    const dc = { no_update: {}, callback_context: { triggered: [] } };
    const window = { dash_clientside: dc };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/review_preferences.js`, 'utf8'), { window });
    return { dc: window.dash_clientside, ...window.dash_clientside.reviewPreferences };
}
const profile = { email: ' Alice@Example.test ' };
const saved = { tabs: { verify: { date: '__all__', device: 'hydrophone-b' }, label: { date: '2026-09-03', device: '__all__' } },
    thresholds: { __global__: .8, Sonar: .9 }, status: 'unverified', classes: ['Other > Ambient sound'] };

test('restores the normalized email owner and all filter controls from browser storage', () => {
    const { restore } = setup();
    const result = restore(profile, { 'alice@example.test': saved });
    assert.equal(result[0].verify.date, '__all__');
    assert.equal(result[0].verify.device, 'hydrophone-b');
    assert.equal(result[0].label.date, '2026-09-03');
    assert.equal(result[1].Sonar, .9);
    assert.equal(result[2][0], 'Other > Ambient sound');
    assert.equal(result[3], 'unverified');
    assert.equal(result[4], .8);
    assert.equal(result[5], 'alice@example.test');
});

test('switching reviewer never inherits another user filters and preserves their stored entry', () => {
    const { restore, remember } = setup();
    let preferences = { 'alice@example.test': saved };
    const b = restore({ email: 'bob@example.test' }, preferences);
    assert.equal(b[0].verify.date, null);
    assert.equal(b[2], null);
    assert.equal(b[3], 'all');
    assert.equal(b[4], .5);
    preferences = remember(b[0], b[1], [], 'verified', { email: 'bob@example.test' }, b[5], preferences);
    assert.deepEqual(JSON.parse(JSON.stringify(preferences['alice@example.test'])), saved);
    assert.equal(restore(profile, preferences)[4], .8);
    assert.equal(restore({ email: 'bob@example.test' }, preferences)[2].length, 0);
});

test('initial defaults and old-owner updates cannot overwrite stored preferences', () => {
    const { dc, remember, persistTabs } = setup();
    const prefs = { 'alice@example.test': saved };
    for (const owner of [null, '__local__', 'bob@example.test']) {
        assert.equal(remember({}, {}, null, 'all', profile, owner, prefs), dc.no_update);
        assert.equal(persistTabs(null, null, 'verify', {}, profile, owner), dc.no_update);
    }
});

test('All Dates, All Devices, no selected classes and a zero threshold survive a round trip', () => {
    const { restore, remember } = setup();
    const tabs = { verify: { date: '__all__', device: '__all__' } };
    const p = remember(tabs, { __global__: 0 }, [], 'mixed', profile, 'alice@example.test', {});
    const restored = restore(profile, p);
    assert.equal(restored[0].verify.date, '__all__');
    assert.equal(restored[0].verify.device, '__all__');
    assert.equal(restored[2].length, 0);
    assert.equal(restored[4], 0);
});

test('malformed stored values get safe defaults without changing the stored object', () => {
    const { restore } = setup();
    const prefs = { 'alice@example.test': { tabs: ['bad'], thresholds: { __global__: 8, X: 'NaN' }, classes: 'bad', status: 'bad' } };
    const original = JSON.stringify(prefs);
    const result = restore(profile, prefs);
    assert.equal(result[0].verify.date, null);
    assert.equal(result[2], null);
    assert.equal(result[3], 'all');
    assert.equal(result[4], .5);
    assert.equal(JSON.stringify(prefs), original);
});

test('tab changes preserve inactive modes and process simultaneous date/device updates', () => {
    const { dc, persistTabs, restore } = setup();
    const tabs = restore(profile, { 'alice@example.test': saved })[0];
    dc.callback_context.triggered = [{ prop_id: 'global-date-selector.value' }, { prop_id: 'global-device-selector.value' }];
    const next = persistTabs('2026-09-04', 'hydrophone-c', 'verify', tabs, profile, 'alice@example.test', [{ value: '2026-09-04' }], [{ value: 'hydrophone-c' }]);
    assert.equal(next.verify.date, '2026-09-04');
    assert.equal(next.verify.device, 'hydrophone-c');
    assert.equal(next.label.date, '2026-09-03');
    assert.equal(tabs.verify.date, '__all__');
});


test('empty discovery options cannot erase a saved device while the date is being restored', () => {
    const { dc, restore, persistTabs } = setup();
    const tabs = restore(profile, { 'alice@example.test': saved })[0];
    dc.callback_context.triggered = [{ prop_id: 'global-device-selector.value' }];
    assert.equal(persistTabs('__all__', null, 'verify', tabs, profile, 'alice@example.test', [], []), dc.no_update);
});
