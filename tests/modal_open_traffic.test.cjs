const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const NO_UPDATE = { no_update: true };
const settle = () => new Promise(resolve => setImmediate(resolve));
const asset = name => fs.readFileSync(`${__dirname}/../app/assets/${name}`, 'utf8');

function loadDisplay() {
    const fetched = [];
    const drawn = [];
    const graph = { data: [{}], layout: { images: [{ source: 'own.png' }], meta: {} } };
    const window = {
        dash_clientside: { no_update: NO_UPDATE },
        setTimeout,
        Plotly: { relayout(_graph, updates) { drawn.push(updates); }, restyle() {} },
    };
    vm.runInNewContext(asset('modal_display_clientside.js'), {
        window,
        console,
        document: {
            querySelector: () => graph,
            createElement: () => ({
                getContext: () => ({
                    createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }),
                    putImageData() {},
                }),
                toBlob: callback => callback({}),
            }),
        },
        URL: { createObjectURL: () => 'blob:drawn', revokeObjectURL() {} },
        fetch(url) {
            fetched.push(url);
            return Promise.resolve({
                ok: true,
                headers: { get: () => '1' },
                arrayBuffer: async () => new ArrayBuffer(4),
            });
        },
    });
    const figure = {
        data: [{}],
        layout: {
            images: [{ source: 'own.png' }],
            yaxis: { type: 'linear' },
            meta: {
                transport_mode: 'full_resolution_lossless_png',
                modal_data_url: '/modal-data/clip',
                raster_tiles: [{ row_start: 0, row_end: 1, column_start: 0, column_end: 1 }],
                raster_palette: [[0, 0, 0], [255, 255, 255]],
                raster_palette_mode: 'listed',
                display_color_min: 39.2229808,
                display_color_max: 70.2397861,
                auto_color_min: 39.2229808,
                auto_color_max: 70.2397861,
            },
        },
    };
    const preview = (drag, committed) => window.dash_clientside.modalDisplay.previewContrast(
        drag, committed, 'linear', figure,
    );
    const commit = (trigger, modalMin, modalMax) => {
        window.dash_clientside.callback_context = { triggered_id: trigger };
        return window.dash_clientside.modalDisplay.updateCommitted(
            'default', 'linear', modalMin, modalMax,
            null, null, null, null, null, null, null, null, null, null, null, null,
            'verify', figure,
        );
    };
    return { fetched, drawn, preview, commit, figure, display: window.hydrophoneModalDisplay };
}

test('a clip opening sets the slider, which fetches and draws nothing', async () => {
    const s = loadDisplay();
    // What the slider sends on open: its old default, then the clip's range.
    s.preview([-90, -10], [-90, -10]);
    s.preview([39.22, 70.24], [39.22, 70.24]);
    await settle();
    assert.deepEqual(s.fetched, []);
    assert.equal(s.drawn.length, 0);
});

test('a clip opening clears the contrast inputs, which fetches nothing', async () => {
    const s = loadDisplay();
    s.commit('modal-colorbar-min-input', null, null);
    await settle();
    assert.deepEqual(s.fetched, []);
});

test('a contrast typed in still redraws, even at the value on screen', async () => {
    const s = loadDisplay();
    await s.commit('modal-colorbar-min-input', 39.2229808, 70.2397861);
    await settle();
    assert.equal(s.fetched.length, 1);
});

test('fetching ahead asks for exactly what a drag will use, except on long clips', async () => {
    const s = loadDisplay();
    await s.display.preloadForContrast(s.figure.layout.meta);
    assert.equal(s.fetched.length, 1);
    s.preview([45, 70.24], [39.22, 70.24]);
    await settle();
    assert.equal(s.fetched.length, 1);
    assert.equal(s.drawn.length, 1);

    const tile = { row_start: 0, row_end: 1, column_start: 0, column_end: 1 };
    await s.display.preloadForContrast({ modal_data_url: '/modal-data/long', raster_tiles: [tile, tile] });
    assert.equal(s.fetched.length, 1);
});

test('a drag draws, and so does moving back to where it began', async () => {
    const s = loadDisplay();
    s.preview([45, 70.24], [39.22, 70.24]);
    await settle();
    assert.deepEqual(s.fetched, ['/modal-data/clip?tile_r0=0&tile_r1=1&tile_c0=0&tile_c1=1']);
    assert.equal(s.drawn.length, 1);
    s.preview([39.22, 70.24], [39.22, 70.24]);
    await settle();
    assert.equal(s.drawn.length, 2);
});

test('the next clip ends a drag, so its slider draws nothing', async () => {
    const s = loadDisplay();
    s.preview([45, 70.24], [39.22, 70.24]);
    await settle();
    s.display.cancelPending();
    s.preview([38.78, 73.42], [38.78, 73.42]);
    await settle();
    assert.equal(s.drawn.length, 1);
});

function loadLifecycle() {
    const images = [];
    const fetched = [];
    const loadedAudio = [];
    const preloaded = [];
    let rawDataArrives = () => {};
    const rawData = { held: false };
    const player = { getAttribute: () => null };
    class FakeImage {
        constructor() { images.push(this); }
        decode() { return Promise.resolve(); }
    }
    const window = {
        dash_clientside: {},
        hydrophoneModalDisplay: {
            cancelPending() {},
            preloadForContrast(meta) {
                preloaded.push(meta.modal_data_url);
                return rawData.held ? new Promise(resolve => { rawDataArrives = resolve; }) : Promise.resolve();
            },
        },
        ensureAudioSourceLoaded(audio) { loadedAudio.push(audio); },
        setTimeout,
        clearTimeout,
        fetch(url) { fetched.push(url); return new Promise(() => {}); },
    };
    vm.runInNewContext(asset('modal_lifecycle_clientside.js'), {
        window,
        console,
        Image: FakeImage,
        document: { querySelector: () => null, getElementById: id => (id === 'modal-player-audio' ? player : null) },
    });
    const open = async (own, neighbours, audio = []) => {
        window.dash_clientside.modalLifecycle.prefetchImages({
            layout: {
                images: own.map(source => ({ source })),
                meta: {
                    modal_data_url: '/modal-data/clip',
                    prefetch_image_urls: neighbours,
                    prefetch_audio_urls: audio,
                },
            },
        });
        await settle();
    };
    const arrive = async source => {
        images.filter(image => image.src === source).forEach(image => image.onload());
        await settle();
    };
    const fail = async source => {
        images.filter(image => image.src === source).forEach(image => image.onerror());
        await settle();
    };
    return {
        fetched,
        loadedAudio,
        preloaded,
        rawData,
        rawDataArrives: async () => { rawDataArrives(); await settle(); },
        player,
        open,
        arrive,
        fail,
        audioMayLoad: () => window.hydrophoneModalLifecycle.audioMayLoad(),
        requested: () => images.map(image => image.src),
    };
}

test('neighbours wait for the whole picture, then go one at a time', async () => {
    const s = loadLifecycle();
    await s.open(['tile-1.png', 'tile-2.png'], ['next.png', 'later.png'], ['next.flac']);
    assert.deepEqual(s.requested(), ['tile-1.png', 'tile-2.png']);
    assert.deepEqual(s.fetched, [], 'no audio ahead of the picture');
    assert.deepEqual(s.preloaded, [], 'no raw data ahead of the picture');

    await s.arrive('tile-1.png');
    assert.deepEqual(s.requested(), ['tile-1.png', 'tile-2.png']);

    await s.arrive('tile-2.png');
    assert.deepEqual(s.requested().slice(2), ['next.png']);
    assert.deepEqual(s.fetched, ['next.flac']);

    await s.arrive('next.png');
    assert.deepEqual(s.requested().slice(2), ['next.png', 'later.png']);
});

test('the raw data follows the picture, and the audio and neighbours follow that', async () => {
    const s = loadLifecycle();
    assert.equal(s.audioMayLoad(), true, 'with no clip open, a player can load');
    s.rawData.held = true;
    await s.open(['own.png'], ['next.png']);
    assert.equal(s.audioMayLoad(), false);

    await s.arrive('own.png');
    assert.deepEqual(s.preloaded, ['/modal-data/clip']);
    assert.equal(s.audioMayLoad(), false);
    assert.deepEqual(s.loadedAudio, []);
    assert.equal(s.requested().includes('next.png'), false);

    await s.rawDataArrives();
    assert.equal(s.audioMayLoad(), true);
    assert.deepEqual(s.loadedAudio, [s.player]);
    assert.equal(s.requested().includes('next.png'), true);
});

test('moving to another clip drops what the last one had queued', async () => {
    const s = loadLifecycle();
    await s.open(['own.png'], ['next.png', 'later.png']);
    await s.arrive('own.png');
    await s.open(['next.png'], ['after.png']);
    await s.arrive('next.png');
    assert.equal(s.requested().includes('later.png'), false);
    assert.equal(s.requested().includes('after.png'), true);
});

test('a picture that fails to load does not stop the neighbours', async () => {
    const s = loadLifecycle();
    await s.open(['broken.png'], ['next.png']);
    await s.fail('broken.png');
    assert.equal(s.requested().includes('next.png'), true);
});
