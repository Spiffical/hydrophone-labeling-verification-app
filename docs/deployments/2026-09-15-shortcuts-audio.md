# Starred labels, modal shortcuts, and audio stability — September 15, 2026

Added reviewer-specific starred label shortcuts to the label editor. Favorites persist in browser local storage by reviewer email; choosing a shortcut uses the existing selection and save workflow. Added left/right arrow navigation and E to open the modal label editor, with typing, slider, nested-dialog, busy-state, and unsaved-change guards.

Visible-frequency audio filtering now preserves its last valid band while Plotly axes are unavailable, waits silently if no valid band exists, and smooths filter/EQ/gain changes. Unchanged polling values do not restart audio parameter automation. An offline native Web Audio test reproduced a severe output spike in the old implementation when the visible window disappeared. The fixed version kept the redraw RMS level within 0.5% and passed rapid frequency changes and filter-disable checks without speaker playback.

Validation:

- Local Python suite: 234 passed, 4 skipped. JavaScript suite: 7 passed.
- Local browser: starred-label saves in Label and Verify modes, persistence, narrow-screen layout, modal shortcuts, typing/slider guards, unsaved-change prompts, and visible-frequency zoom updates.
- Server runtime: 52 targeted favorite-label, review-queue, and audio tests passed.
- Live HTTP: ports 18053 and 18051 returned 200. Updated JavaScript/CSS asset hashes match the manifest, and the live layout contains the favorites store.

Deployed 13 files to `/home/sbialek/ONC/hydrophone-review-current` on oncvm-daq after verifying every previous file hash against the expected source. Backup, staged files, and manifest are under `/home/sbialek/ONC/review-shortcuts-audio-20260915/`; rollback archive: `before-deployment.tar.gz`. The manifest records newly added files separately with null prior hashes, so rollback also needs to remove those newly added files.

Only screen session `verify-september-2026` was restarted through `/home/sbialek/ONC/run_september_review.sh`. Live endpoint: http://142.104.222.2:18053/. No review data or dataset configuration was changed by deployment or live verification.
