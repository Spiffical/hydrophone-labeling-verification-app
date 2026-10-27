const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const NO_UPDATE = { no_update: true };

function load() {
    const renders = [];
    const window = {
        dash_clientside: { no_update: NO_UPDATE },
        hydrophoneModalLifecycle: { beginRender() { renders.push(Date.now()); } },
    };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/modal_display_clientside.js`, 'utf8'), { window, console });
    const refresh = (trigger, colormap, yAxisScale, figure) => {
        window.dash_clientside.callback_context = { triggered_id: trigger };
        // Copied out of the sandbox, whose arrays have their own prototype.
        return Array.from(window.dash_clientside.modalDisplay.startViewRefresh(colormap, yAxisScale, figure));
    };
    return { refresh, renders };
}

function figure(colormap, yAxisType) {
    return { layout: { meta: { modal_item_id: 'clip', display_colormap: colormap }, yaxis: { type: yAxisType } } };
}

test('a clip opening with toggles that match its figure shows no "Updating spectrogram"', () => {
    // The open sets both toggles in the same answer as the figure drawn with them. No redraw
    // follows, so an overlay set here (after the figure's finishLoading) would never clear.
    const s = load();
    assert.deepEqual(s.refresh('modal-colormap-toggle', 'default', 'linear', figure('default', 'linear')), [NO_UPDATE, NO_UPDATE]);
    assert.deepEqual(s.refresh('modal-y-axis-toggle', 'hydrophone', 'log', figure('hydrophone', 'log')), [NO_UPDATE, NO_UPDATE]);
    assert.equal(s.renders.length, 0);
});

test('a colormap or y-axis change the figure was not drawn with shows it until the redraw', () => {
    const s = load();
    assert.deepEqual(s.refresh('modal-colormap-toggle', 'hydrophone', 'linear', figure('default', 'linear')), [true, false]);
    assert.deepEqual(s.refresh('modal-y-axis-toggle', 'default', 'log', figure('default', 'linear')), [true, false]);
    // Without a drawn clip to compare with, as before.
    assert.deepEqual(s.refresh('modal-colormap-toggle', 'default', 'linear', null), [true, false]);
    assert.equal(s.renders.length, 3);
});

test('other triggers leave the overlay alone', () => {
    const s = load();
    assert.deepEqual(s.refresh('modal-colorbar-min-input', 'hydrophone', 'linear', figure('default', 'linear')), [NO_UPDATE, NO_UPDATE]);
});
