# All Dates indexing performance — September 14, 2026

The shared-drive dataset contains 8,939 unique clips across 83 spectrogram folders. The existing loader repeatedly checked individual paths and scanned the same audio folders for fallback matches.

## Measurements on oncvm-daq

- Existing dashboard log: 27.1 seconds for background indexing; network filesystem timings vary between runs.
- Profiled baseline: 54.37 seconds, including 52,532 `stat` calls taking 40.83 seconds. Reading the 37 prediction JSON files took about 0.33 seconds. The unified converter's relative-path checks consumed 24.24 seconds; audio enrichment consumed 21.20 seconds.
- Profiled optimized loader: 12.61 seconds. Audio enrichment dropped to 0.63 seconds and existing audio-path resolution to 0.35 seconds.
- Subsequent unprofiled comparison on the same dataset: **51.41 seconds before / 8.07 seconds after**, about **6.4× faster**. These are loader times, excluding card-image transfer/rendering. Shared-drive caching and concurrent traffic affect wall-clock results.
- The before/after item identifiers, order, all media paths, device identifiers, and prediction contents matched exactly for all 8,939 clips.

## Implementation

`DirectoryIndex` snapshots each directory once per dataset load. Relative-path conversion, media lookup, and spectrogram discovery reuse those listings instead of performing one remote `stat` per candidate path. Audio timestamp fallback reuses the already-listed files rather than globbing three times for every clip. Existing extension priority and segment-isolation behavior are preserved.

Snapshots are local to a load, not a long-lived filesystem cache. A subsequent reload sees newly added/deleted files. Broken symlinks are checked against their targets, and unlistable parent directories fall back to ordinary path checks. The existing persistent All Dates index and background refresh behavior remain intact.

Removed the artificial three-second delay after the preview-ready signal. Indexing still waits for the preview response; it then starts immediately.

## Validation and deployment

- Local suite: **212 passed, 4 skipped**.
- Server suite: **44 passed** across data loading, filesystem indexing, review-queue updates, and All Dates loading. Staging required the repository's mock-data fixtures before the three fixture-dependent loading tests could run.
- Added regressions for thousands of checks sharing one listing, fresh reloads, missing paths, broken symlinks, permissions fallback, relative paths, timestamp matching, and segment isolation.
- Deployed background refresh completed in **3.7 seconds**, including persistence, on the latest live run. Both ports 18053 and 18051 returned HTTP 200.
- Live browser after restart: All Dates displays **8,939 recordings**, **8,579 matching clips**, **8,380 left to verify**, and 16 first-page cards under the default filters at check time. No browser errors were reported. No review data was saved during this work.

Six files (including one regression test file) were deployed to `/home/sbialek/ONC/hydrophone-review-current`. Before/after SHA-256 values are in `2026-09-14-all-dates-speed-manifest.json`. Every deployed file matched the expected pre-change source before replacement.

Remote backup and manifest: `/home/sbialek/ONC/all-dates-speed-20260914/`. Only `verify-september-2026` on port 18053 was restarted through the existing launcher. The dataset configuration and other dashboards were preserved.
