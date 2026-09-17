# Safari visible-frequency playback follow-up — September 16, 2026

Tested after deployment, in native Safari 26.5.2 (build 21624.2.5.11.8).

## Live dashboard

Opened `http://142.104.222.2:18053/`, selected September 3, page 15, and opened the reported recording `ICLISTENHF6324_20260903T195000.000Z_20260903T195454.500Z-OD-spect_plotRes` (item 239/288).

Enabled **Only play visible frequencies**, set playback to 0.75x, and played while using Zoom in, Zoom out, and Home/Reset axes repeatedly. The band readout followed the plot: approximately 6.4–19 kHz after one zoom, 9.6–16 kHz after another, and the full 0.1 Hz–25.59 kHz range after Home. Playback advanced to 23 seconds and was then paused. No labels or annotations were changed. Temporary speed/filter settings were restored before leaving the page.

The live UI test checked playback progression and filter/window synchronization; output signal measurements below used a separate local harness.

## Measured native Safari stress test

Downloaded the deployed audio and modal-lifecycle assets and verified their hashes against the deployment manifest. Used the actual reported FLAC, starting at 210 seconds, with 0.75x playback and 24.1x amplification. The local test used a real HTML media element, the deployed audio controls, and Plotly from local Python package 6.8.0. Plotly alternated frequency windows every half second (10–20 kHz, full range, 18–25.59 kHz, and 100–1000 Hz), also exercising log-axis changes and autorange resets through the deployed lifecycle guard.

An analyser sampled the output before a zero-gain speaker connection. Safari's tab mute was OFF. An initial run with Safari's tab mute ON produced zero samples; those stopped after unmuting. That run was discarded and the page reloaded for a clean test. Muting at the final gain node kept the clean test silent without interfering with the measured signal.

Clean run results:

- Duration: 90.043 seconds, source playback advanced from 210 to 277.122 seconds.
- 181 plot updates, including 30 resets; visible-only mode stayed enabled.
- 847 measured frames after the first two seconds of startup.
- Zero silent frames (RMS threshold 1e-9), zero nonfinite samples, zero media waiting events.
- Peak: 0.0334745 (full-scale clipping threshold is 1).
- RMS range: 0.0002140–0.0235214, varying with the selected band and recording.
- One intentional initial seek. Three rate-change events across setup/playback; speed readout remained 0.75x.

No dropout or excessive level spike was reproduced in this clean run. This is an instrumented test, not a subjective listening confirmation on the coworker's hardware. No additional production changes were needed.

The temporary Safari tab and local server were closed after verification. Diagnostic harness and media are under `/tmp/audio-redraw-20260916/` and are not part of the production app.
