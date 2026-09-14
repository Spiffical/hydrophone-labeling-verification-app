# Unified review app — September 14, 2026

The canonical checkout now combines the active anomaly-review dashboard, its September 14 review/viewport fixes, and the approved multi-range features from `whale-call-analysis/analysis/hydrophone_verification_app_multi_range_20260831`.

## User-visible behavior

- Frequency presets and custom range controls appear only after selecting **Generate from audio**, in Label, Verify, and Explore. Existing files render one spectrogram and ignore retained multi-range selections; switching back restores the choices.
- Select up to five visible ranges, apply them, and generate spectrograms. Built-in defaults cover low, mid, social, high, and ultrasonic frequencies. Dataset configurations can supply their own presets. Custom ranges can be named, shown/hidden, and removed.
- Cards stack selected ranges from high to low. The modal shows separate interactive Plotly panels in the same order; bounding-box editing belongs to the active range. Its figure and heading now resolve the same selected range, including the FFT configuration, instead of inheriting a full-page frequency scale.
- Application Settings offers 1–8 rows and 1–6 columns; their product determines page capacity. Cards use square spectrograms and adapt to narrow screens. Viridis is the default colormap. Range images load lazily and use the image cache.
- The All Dates loader invalidates cached results when its predictions file changes and releases empty previews instead of waiting indefinitely.
- Edit labels wording, explicit page numbers, filtered remaining counts, immediate grid refresh after saving, full-cache preservation, and viewport-safe settings/modal behavior remain in place.
- Manual-review queues, provisional labels without model scores, recommendation metadata, and source/Nyquist diagnostics are retained.

## Verification

- Full local Python suite: **206 passed, 4 skipped** (opt-in live tests).
- JavaScript modal performance regression: **1 passed**.
- Server-runtime regression suite: **47 passed**, covering review queue updates, ranges, grid sizing, and All Dates loading.
- Disposable six-clip browser dataset: existing/generated source switching, two presets plus a custom range, preserved selections, square images, grid resizing, and multi-panel modal rendering. Card Save and modal Save changed remaining counts 6 → 5 → 4 and removed only the saved clips from Unverified only. The final modal correction was checked against its rendered 5–125 Hz axis.
- Responsive browser checks include a 390 × 700 viewport. Live September 7 data loads all 16 first-page images and displays 274 clips remaining / 275 matching under the default filters at verification time. Both Close controls and modal navigation remain accessible. No browser errors were reported.
- All review writes during this unification were confined to disposable local QA data; no test reviews were saved to the live archive.

## Deployment and provenance

Updated 46 files on oncvm-daq in `/home/sbialek/ONC/hydrophone-review-current`. Every source file was compared against the initial live snapshot before deployment; no intervening changes were found. SHA-256 values before/after are recorded in `2026-09-14-unified-app-manifest.json`.

Only screen session `verify-september-2026` was restarted using `/home/sbialek/ONC/run_september_review.sh`. The active app is http://142.104.222.2:18053/. Ports 18053 and 18051 both returned HTTP 200 afterward.

Deployment archive, manifest, staging tree, and rollback archive are under `/home/sbialek/ONC/unified-review-20260914/`; the rollback archive is `before-deployment.tar.gz`. Existing dataset config `/home/sbialek/ONC/september-2026-review.yaml`, shared review files, watchdog, and other dashboard processes were preserved.

This supersedes the earlier warning that this checkout lacks live command-bar/All Dates functionality. Use this shared app with separate dataset configuration files rather than continuing separate feature forks. The other whale dashboard processes have not been repointed or restarted in this deployment. Their unrelated label-attributes schema changes were outside the approved feature list and are not part of this import; audit that compatibility before migrating those running instances.
