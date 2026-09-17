# Safari audio and Home/reset verification — 2026-09-16

Local changes only; no production files or annotations were changed.

## Audio finding

Used the reported recording `ICLISTENHF6324_20260903T195000.000Z.flac`, source seconds 210–260, at 0.75x playback and 24.1x amplification. Native Safari OfflineAudioContext rendered 60 seconds at 48 kHz without speaker output. With the deployed code, the supposedly bypassed 0.001 Hz highpass remained in the signal path. Isolating that stage reproduced growing signal error in Safari; Chromium did not show the same error.

| Safari path | Peak | RMS |
| --- | ---: | ---: |
| Direct reference | 0.031644 | 0.009217 |
| Old full-range path | 0.065857 | 0.019731 |
| Isolated old highpass | 0.065914 | 0.019731 |
| New full-range path | 0.031644 | 0.009217 |
| New visible-only, repeated zooms | 0.028374 | 0.006027 |
| New alternating enabled/disabled mode | 0.028374 | 0.007301 |

The new filter stages have complementary dry/wet gain paths with 25 ms smoothing. Disabled filters and frequency windows reaching zero/Nyquist use the dry path. Active cutoffs have a 1 Hz lower bound, reported as clamped when applicable, avoiding the old near-zero coefficients. All new nodes are disconnected on player cleanup.

Native Safari media-element streaming was also tested on the real FLAC, starting at 220 seconds, for 30 seconds per mode. Frequency windows alternated every half second between 10–20 kHz and the full band. An analyser measured output before a zero-gain speaker connection. Both modes had zero silent analyser frames after startup and zero waiting events. Peak was 0.031571 with filtering off and 0.027574 with filtering on. There was one initial seek per run; rate changes were confined to initial setup.

This reproduces a Safari signal-processing defect and verifies its removal; it does not prove that every previously reported audible dropout/rattle had this single cause. Measurements were silent, not a listening test on the coworker's machine.

## Home/reset

The existing guard only handled `autorange: true`. Plotly Home can instead restore its saved initial ranges, bypassing that guard. Home now explicitly restores the current recording's canonical metadata ranges and full raster; a queued reset cannot overwrite the next recording after navigation.

Verified the reported MAT recording in the local dashboard in native Safari and in-app Chromium: zoom in, then Home restores the full time span and frequency extent. Chromium additionally verified a selected 10–20 kHz window on linear and log axes. The original intermittent overly wide view was not reproduced deterministically; the explicit reset removes reliance on Plotly's remembered initial bounds.

## Reusable checks

- `node --test tests/*.test.cjs`: 13 passed.
- `.venv/bin/python -m pytest -q`: 234 passed, 4 skipped.
- `tests/audio_signal_regression.html`, served locally: passed in native Safari and Chromium. Includes redraws with missing axes, rapid filter changes, and a 60-second full-range waveform comparison. Maximum full-range error was 1.1933e-9 in both browsers.
- `tests/modal_axis_reset.test.cjs`: current bounds, log-unit conversion, ordinary zoom preservation, autorange fallback, and navigation during a pending reset.

Temporary browser tabs and local QA servers were closed after testing. Real media and disposable fixture annotations remain outside the repository under `/tmp`.
