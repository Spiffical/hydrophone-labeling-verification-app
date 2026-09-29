const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

async function setup(logarithmic = false) {
    const handlers = {}, clicks = {}, frames = [], resets = [];
    const graph = {
        layout: { meta: { modal_item_id: 'clip', x_min: 0, x_max: 5,
            y_to_hz: 1000, display_y_min_hz: 10, display_y_max_hz: 20000 },
            xaxis: { range: [2, 3] }, yaxis: { type: logarithmic ? 'log' : 'linear' } },
        on(name, handler) { handlers[name] = handler; },
        addEventListener(name, handler, capture) { clicks[name] = { handler, capture }; },
        contains: () => true,
    };
    const raf = fn => { frames.push(fn); };
    const sandbox = { console, requestAnimationFrame: raf, document: { querySelector: () => graph },
        window: { requestAnimationFrame: raf, dash_clientside: {}, Plotly: {
            relayout(g, updates) { resets.push(updates); return Promise.resolve(); },
        } } };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/modal_lifecycle_clientside.js`, 'utf8'), sandbox);
    async function flush() {
        for (let i = 0; i < 10; i++) {
            while (frames.length) frames.shift()();
            await Promise.resolve();
        }
    }
    const ready = sandbox.window.dash_clientside.modalLifecycle.finishLoading(graph);
    await flush(); await ready;
    return { graph, handlers, clicks, resets, flush, window: sandbox.window };
}

test('Home uses current spectrogram bounds instead of Plotly initial ranges, including log units', async () => {
    for (const logarithmic of [false, true]) {
        const s = await setup(logarithmic);
        assert.equal(s.clicks.click.capture, true);
        const event = { target: { closest: () => ({}) },
            preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
        s.clicks.click.handler(event);
        await s.flush();
        assert.equal(event.prevented, true);
        assert.equal(event.stopped, true);
        assert.equal(JSON.stringify(s.resets[0]), JSON.stringify({
            'xaxis.autorange': false, 'xaxis.range': [0, 5], 'yaxis.autorange': false,
            'yaxis.range': logarithmic ? [-2, Math.log10(20)] : [.01, 20],
        }));
    }
});

test('ordinary zoom is preserved and autorange resets to the selected frequency window', async () => {
    const s = await setup();
    s.handlers.plotly_relayout({ 'yaxis.range': [10, 15] });
    await s.flush(); assert.equal(s.resets.length, 0);
    s.graph.layout.meta.display_y_max_hz = 12000;
    s.handlers.plotly_relayout({ 'yaxis.autorange': true });
    await s.flush();
    assert.equal(s.resets[0]['yaxis.range'][1], 12);
});

test('pending Home reset cannot apply an earlier recording range after navigation', async () => {
    const s = await setup();
    s.handlers.plotly_relayout({ 'xaxis.autorange': true });
    s.graph.layout.meta.modal_item_id = 'next-clip';
    await s.flush();
    assert.equal(s.resets.length, 0);
    assert.equal(s.graph._hydrophoneAxisResetPending, false);
});

test('on a long clip, Home returns to the page on screen as a GUI edit', async () => {
    const s = await setup();
    const guiResets = [];
    s.window.modalPaging = {
        homeRange: () => [2, 3],
        relayout(graph, updates) { guiResets.push(updates); return Promise.resolve(); },
    };
    const event = { target: { closest: () => ({}) }, preventDefault() {}, stopImmediatePropagation() {} };
    s.clicks.click.handler(event);
    await s.flush();
    assert.equal(s.resets.length, 0, 'not a plain relayout, which Dash re-plots would undo');
    assert.deepEqual(Array.from(guiResets[0]['xaxis.range']), [2, 3]);
    assert.deepEqual(Array.from(guiResets[0]['yaxis.range']), [.01, 20]);
});

test('zoom rasters map columns to the image, which starts half a window into a clip-time axis', async () => {
    const s = await setup();
    const crop = s.window.hydrophoneModalLifecycle.visibleRasterCrop;
    // 391 frames, centres 0.125-9.875 s on a 0-10 s axis (a 0.25 s window).
    const graph = { layout: {
        meta: { x_min: 0, x_max: 10, image_x_min: 0.125, image_x_max: 9.875, source_matrix_shape: [100, 391],
            modal_image_url: '/modal-image/t', y_to_hz: 1, data_y_min_hz: 0, data_y_max_hz: 100 },
        xaxis: { range: [2, 4] }, yaxis: { range: [0, 100] } }, clientWidth: 800, clientHeight: 400 };
    const zoomed = crop(graph);
    // 40 columns per second from 0.125 s, with an 8% margin either side.
    assert.equal(zoomed.columnStart, 68);
    assert.equal(zoomed.columnEnd, 163);
    assert.ok(Math.abs(zoomed.x - 1.825) < 1e-9);
    // Figures from before image_x_min fall back to the axis bounds.
    delete graph.layout.meta.image_x_min;
    delete graph.layout.meta.image_x_max;
    assert.equal(crop(graph).columnStart, 71);
});
