# Safari audio and Home/reset deployment — September 16, 2026

Deployed the two tested browser assets to `/home/sbialek/ONC/hydrophone-review-current` on `oncvm-daq` at approximately 20:29 UTC:

- `app/assets/audio_controls.js`: true dry/wet bypass for visible-frequency filters, smooth switching, and a stable lower cutoff.
- `app/assets/modal_lifecycle_clientside.js`: Home explicitly restores current spectrogram bounds and avoids applying a pending reset to a different recording.

Baseline SHA-256 values matched local HEAD `260c5cf059d6da0bf44c4da758f76c9825225d44` before replacement. The adjacent manifest records previous and deployed hashes. Local regression suite: 13 JavaScript tests passed; prior local Python run: 234 passed, 4 skipped. Native Safari and Chromium verification is documented in `docs/qa/2026-09-16-safari-audio-home.md`.

Staging and rollback backup: `/home/sbialek/ONC/review-safari-audio-home-20260916/`. The rollback archive `before-deployment.tar.gz` contains both original assets. To roll back, restore that archive into the app directory, restart only `verify-september-2026`, and run `/home/sbialek/ONC/run_september_review.sh`.

Restarted only the September review screen; new session `347087.verify-september-2026`. HTTP checks on port 18053 for the app, Dash layout, and both assets returned 200. Served asset hashes exactly match the deployment manifest. The separate dashboard on port 18051 also returned 200 and its screen session was untouched.

No review data, saved labels, or dataset configuration was changed. Source changes remain local; this deployment did not push GitHub branches.

Live browser smoke test passed: September 3 review cards loaded, the 00:15 recording opened, zoom narrowed the axes, and Home restored the initial extent (time ticks 0–4.5 minutes and frequency ticks 0–25 kHz). No browser console errors were reported. The temporary check tab was closed.
