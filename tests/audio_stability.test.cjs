const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

function setup() {
    let graph = { _fullLayout: { yaxis: { range: [1, 2], title: { text: 'kHz' } } } };
    const sandbox = { window: {}, document: {
        addEventListener() {},
        getElementById: () => ({ querySelector: () => graph }),
    } };
    vm.runInNewContext(fs.readFileSync(`${__dirname}/../app/assets/audio_controls.js`, 'utf8'), sandbox);
    function param() {
        return { value: 0, calls: [], cancelAndHoldAtTime(t) { this.calls.push(['hold', t]); },
            setValueAtTime(v, t) { this.value = v; this.calls.push(['set', v, t]); },
            setTargetAtTime(v, t, tau) { this.value = v; this.calls.push(['target', v, t, tau]); } };
    }
    const context = { currentTime: 1, sampleRate: 48000 };
    const audio = { audioContext: context, playbackRate: 1, requestedGain: 10,
        paused: false, userRequestedPlayback: true,
        gainNode: { gain: param() },
        visibleHighpassFilter: { context, frequency: param(), bypassDry: { gain: param() }, bypassWet: { gain: param() } },
        visibleLowpassFilter: { context, frequency: param(), bypassDry: { gain: param() }, bypassWet: { gain: param() } } };
    return { sandbox, audio, setGraph: (value) => { graph = value; } };
}

test('plot redraw never expands a valid visible-only band to full-range audio', () => {
    const { sandbox: s, audio, setGraph } = setup();
    s.updateVisibleFrequencyFilters(audio, true);
    const low = audio.visibleLowpassFilter.frequency;
    assert.equal(low.value, 2000);
    const count = low.calls.length;
    setGraph(null);
    assert.equal(s.updateVisibleFrequencyFilters(audio, true).waiting, true);
    assert.equal(low.value, 2000);
    assert.equal(low.calls.length, count);
});

test('missing initial axes mute output until a valid band is applied, even with gain polling', () => {
    const { sandbox: s, audio, setGraph } = setup();
    setGraph({ data: [{ y: [0, 24000] }], _fullLayout: {} });
    s.updateVisibleFrequencyFilters(audio, true);
    s.setAudioGainValue(audio, 50);
    assert.equal(audio.gainNode.gain.value, 0);
    setGraph({ _fullLayout: { yaxis: { range: [300, 600] } } });
    s.updateVisibleFrequencyFilters(audio, true);
    assert.equal(audio.visibleLowpassFilter.frequency.value, 600);
    assert.equal(audio.visibleLowpassFilter.frequency.calls.at(-1)[0], 'set');
    assert.equal(audio.gainNode.gain.value, 10);
});

test('filter movements are smoothed and unchanged polls do not restart automation', () => {
    const { sandbox: s, audio, setGraph } = setup();
    s.updateVisibleFrequencyFilters(audio, true);
    const freq = audio.visibleLowpassFilter.frequency;
    const count = freq.calls.length;
    for (let i = 0; i < 30; i++) s.updateVisibleFrequencyFilters(audio, true);
    assert.equal(freq.calls.length, count);
    setGraph({ _fullLayout: { yaxis: { range: [2, 3], title: 'kHz' } } });
    s.updateVisibleFrequencyFilters(audio, true);
    assert.deepEqual(freq.calls.at(-1), ['target', 3000, 1, .025]);
});

test('log axes and pitch shift map to finite cutoffs, disabling restores full range', () => {
    const { sandbox: s, audio, setGraph } = setup();
    setGraph({ _fullLayout: { yaxis: { type: 'log', range: [2, 3], title: 'Hz' } } });
    audio.playbackRate = 2;
    const state = s.updateVisibleFrequencyFilters(audio, true);
    assert.equal(state.cutoffMinHz, 200);
    assert.equal(state.cutoffMaxHz, 2000);
    s.updateVisibleFrequencyFilters(audio, false);
    assert.equal(audio.visibleHighpassFilter.frequency.value, 200);
    assert.equal(audio.visibleHighpassFilter.bypassDry.gain.value, 1);
    assert.equal(audio.visibleHighpassFilter.bypassWet.gain.value, 0);
    assert.equal(audio.visibleLowpassFilter.bypassDry.gain.value, 1);
    assert.equal(audio.lastVisibleFilterState, null);
    assert.equal(audio.visibleFilterWaiting, false);
});


test('full-range and zero-Hz windows bypass filters without moving cutoffs toward zero', () => {
    const { sandbox: s, audio, setGraph } = setup();
    s.updateVisibleFrequencyFilters(audio, true);
    const hp = audio.visibleHighpassFilter, lp = audio.visibleLowpassFilter;
    assert.equal(hp.bypassWet.gain.value, 1);
    const previousCalls = hp.frequency.calls.length;
    setGraph({ _fullLayout: { yaxis: { range: [0, 24000], title: 'Hz' } } });
    const state = s.updateVisibleFrequencyFilters(audio, true);
    assert.equal(state.cutoffMinHz, 0);
    assert.equal(state.cutoffMaxHz, 24000);
    assert.equal(hp.frequency.calls.length, previousCalls);
    assert.equal(hp.bypassWet.gain.value, 0);
    assert.equal(lp.bypassWet.gain.value, 0);
    const bypassCalls = hp.bypassDry.gain.calls.length;
    for (let i = 0; i < 100; i++) s.updateVisibleFrequencyFilters(audio, false);
    assert.equal(hp.frequency.calls.length, previousCalls);
    assert.equal(hp.bypassDry.gain.calls.length, bypassCalls);
});

test('bypassable filters route dry and filtered paths to the same output and clean up all nodes', () => {
    const { sandbox: s } = setup();
    const nodes = [];
    const context = {
        createGain: () => node(), createBiquadFilter: () => node(),
    };
    function node() {
        const n = { context, frequency: {}, Q: {}, gain: {}, outputs: [],
            connect(other) { this.outputs.push(other); }, disconnect() { this.outputs = []; } };
        nodes.push(n); return n;
    }
    const filter = s.createBypassableFilter(context, 'highpass');
    assert.equal(filter.frequency.value, 1000);
    assert.equal(filter.bypassDry.gain.value, 1);
    assert.equal(filter.bypassWet.gain.value, 0);
    assert.deepEqual(filter.bypassInput.outputs, [filter.bypassDry, filter]);
    assert.deepEqual(filter.outputs, [filter.bypassWet]);
    assert.deepEqual(filter.bypassDry.outputs, [filter.bypassOutput]);
    assert.deepEqual(filter.bypassWet.outputs, [filter.bypassOutput]);
    s.disconnectBypassableFilter(filter);
    assert.ok(nodes.every(n => n.outputs.length === 0));
});


test('very small positive frequency windows cannot reintroduce near-zero highpass coefficients', () => {
    const { sandbox: s, audio, setGraph } = setup();
    setGraph({ _fullLayout: { yaxis: { range: [.1, 24000], title: 'Hz' } } });
    audio.playbackRate = .75;
    const state = s.updateVisibleFrequencyFilters(audio, true);
    assert.equal(audio.visibleHighpassFilter.frequency.value, 1);
    assert.equal(state.clamped, true);
});

test('the playback line sits on the sound: x = 0 is the first frame, half a window in', () => {
    const { sandbox: s, setGraph } = setup();
    const graph = {
        layout: {
            meta: { x_min: 0, x_max: 9.75, x_to_seconds: 1, x_origin_seconds: 0.125 },
            shapes: [{ x0: 0, x1: 0, line: {} }],
        },
        _fullLayout: {},
    };
    setGraph(graph);
    s.updateSpectrogramPlaybackMarker(5, 10);
    assert.equal(graph.layout.shapes[0].x0, 4.875);
    // Figures without an origin (existing spectrogram files) are unchanged.
    delete graph.layout.meta.x_origin_seconds;
    s.updateSpectrogramPlaybackMarker(5, 10);
    assert.equal(graph.layout.shapes[0].x0, 5);
});

test('a replaced or removed player stops downloading but keeps its source for later', () => {
    const { sandbox: s } = setup();
    function element(src) {
        const attrs = { src: src, 'data-audio-src': src };
        return { attrs, loads: 0, pauses: 0, isConnected: true,
            hasAttribute(name) { return name in attrs; },
            getAttribute(name) { return name in attrs ? attrs[name] : null; },
            removeAttribute(name) { delete attrs[name]; },
            load() { this.loads += 1; }, pause() { this.pauses += 1; } };
    }
    // The modal's next clip replaces the player: the old file stops loading.
    const first = element('/audio-file/first');
    const second = element('/audio-file/second');
    s.ensureAudioPlayerEntry('modal-player', first);
    s.ensureAudioPlayerEntry('modal-player', second);
    assert.equal(first.attrs.src, undefined);
    assert.equal(first.loads, 1);
    assert.equal(first.attrs['data-audio-src'], '/audio-file/first');
    assert.equal(second.attrs.src, '/audio-file/second');
    assert.equal(second.loads, 0);
    // Closing the modal removes it: same.
    second.isConnected = false;
    s.cleanupDetachedAudioPlayers();
    assert.equal(second.attrs.src, undefined);
    assert.equal(second.loads, 1);
    assert.ok(second.pauses >= 1);
});
