# Anomaly review on oncvm — November 5, 2026

The redesigned Verify page runs on `oncvm` at http://142.104.198.24:8088/ (ONC network or connected UVic VPN) while `oncvm-daq` is unreachable. The dashboard at http://142.104.222.2:18053/ has been unreachable since about October 24.

## Where it is

- Folder: `/home/sbialek/ONC/anomaly-review/`
- Build: `app_3d2f1f2_queue_fix/`, which is commit `3d2f1f2` plus `DEPLOYED_PATCH.diff`. `SHA256SUMS` inside lists every file.
- Config: `config.yaml`. It is `oncvm-daq`'s `review.yaml` with a 3×3 grid, `cache.max_size: 48` because the VM is shared, and `date: 2026-10-05`, the newest day with predictions. Without a date the page opens on the newest folder, which has none.
- Server: screen `anomaly-review`, log `logs/server.log`, venv `~/ONC/hydrophone-labeling-verification-app/.venv`. Start it from the app folder, because that venv holds an older install of the app.
- Reboots: start line in `oncvm_restart_after_reboot.sh` in the whale-call-analysis repo.

## Page hang found on the live server

Over the VPN the first build sat on "Preparing page" on every load, with 13 callbacks in Dash's `requested` list and nothing running. Local runs never showed it.

The app's callbacks form loops. Dash breaks a loop only on a queue pass where nothing else is pending, and a pass does not re-run for its own changes. When the last pass merges duplicate requests, nothing wakes the queue again. Dispatching `Callbacks.Completed` by hand on a stuck page freed it at once.

`app/assets/dash_queue_watchdog.js` does that when the same waiting list has sat for a full second with nothing running.

| Build | Config | Result through the VPN proxy |
|---|---|---|
| Without the fix | No date | Stuck on every load |
| Without the fix | Pinned date | Stuck on every load |
| With the fix | No date | 3 of 3 loaded |
| With the fix | Pinned date | Every load finished |

## Verification

- `oncvm`'s Python 3.10: 401 passed, 4 skipped. Local JavaScript: 122 passed.
- Live read-only check through the proxy, with no reviewer profile: first load, day changes, a day with no predictions, opening and closing a clip, All Dates (about 15 seconds). No console errors or server tracebacks.
- Counts match the archive: 2026-03-02 shows 181 verified clips in range and 183 of 284 verified. All Dates shows 231 of 19,710, and the archive holds 19,710 unique clips because 546 appear in two day folders.
- All 94 review files hash the same as before the first start, and no archive file is newer than that start.
- Not checked: a save on the live archive, audio playback, Safari.

## Rollback

Copies of all 94 review files from before this build could write to them are in `backups/predictions-before-20261105T060856Z.tar.gz`, with a second copy in `oncvm_ONC/verification_backups/anomaly-review-20261105T060856Z/` on WhaleStor. `app_3d2f1f2/` is the build without the fix.

To stop the dashboard, run `screen -S anomaly-review -X quit`. If `oncvm-daq` comes back, use only one of the two dashboards, because both write to the same review files.
