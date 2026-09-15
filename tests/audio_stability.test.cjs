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
        visibleHighpassFilter: { context, frequency: param() },
        visibleLowpassFilter: { context, frequency: param() } };
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
    assert.equal(audio.visibleHighpassFilter.frequency.value, .001);
    assert.equal(audio.lastVisibleFilterState, null);
    assert.equal(audio.visibleFilterWaiting, false);
});
