# Reviewer preferences deployment — September 16, 2026

Deployed the seven application files for per-reviewer filter persistence to
`/home/sbialek/ONC/hydrophone-review-current` on `oncvm-daq` at approximately
21:27 UTC. Existing files matched local HEAD
`260c5cf059d6da0bf44c4da758f76c9825225d44` before replacement. The two new files
were absent before deployment.

The remote deployment directory `/home/sbialek/ONC/review-preferences-20260916`
contains `manifest.json` with before/after SHA-256 values, `update.tar.gz`, and
`before-deployment.tar.gz`. All deployed hashes matched the manifest. Python
sources compiled successfully before application.

Restarted only the September review dashboard, now screen session
`348649.verify-september-2026`. The app, layout, callback dependencies, and new
JavaScript asset returned HTTP 200. All three clientside preference functions
were registered, and the served JavaScript matched its expected hash. The
separate dashboard on port 18051 remained healthy and was not restarted.

Live browser verification with a browser-local QA profile confirmed September 3,
ICLISTENHF6324, unverified status, 52% threshold, and all classes survived reload;
281 matching clips rendered from 289 recordings. No browser console errors or
server exceptions were found. No annotation or review data was changed.
Full local profile-switching and class-selection coverage is recorded in
`docs/qa/2026-09-16-review-preferences.md`.

Preferences persist by reviewer email in the same browser. Existing open tabs
need to reload to receive the update. No GitHub push was performed.

To roll back, restore `before-deployment.tar.gz` into the app root, remove the two
new files `app/assets/review_preferences.js` and
`app/callbacks/ui/review_preferences_callbacks.py`, then restart only the
`verify-september-2026` screen using `/home/sbialek/ONC/run_september_review.sh`.
