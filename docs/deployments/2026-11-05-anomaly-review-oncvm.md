# Anomaly review on oncvm — November 5, 2026

The redesigned Verify page runs on `oncvm` at http://142.104.198.24:8088/ (ONC network or connected UVic VPN) while `oncvm-daq` is unreachable. The dashboard at http://142.104.222.2:18053/ has been unreachable since about October 24.

## Where it is

- Folder: `/home/sbialek/ONC/anomaly-review/`
- Build: `app_2ebf6fa/`, which is commit `2ebf6fa`. `SHA256SUMS` inside lists every file.
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

## Verification of the first build

The first build was `app_3d2f1f2_queue_fix/`, commit `3d2f1f2` plus `DEPLOYED_PATCH.diff`.

- `oncvm`'s Python 3.10: 401 passed, 4 skipped. Local JavaScript: 122 passed.
- Live read-only check through the proxy, with no reviewer profile: first load, day changes, a day with no predictions, opening and closing a clip, All Dates (about 15 seconds). No console errors or server tracebacks.
- Counts match the archive: 2026-03-02 shows 181 verified clips in range and 183 of 284 verified. All Dates shows 231 of 19,710, and the archive holds 19,710 unique clips because 546 appear in two day folders.
- All 94 review files hash the same as before the first start, and no archive file is newer than that start.
- Not checked: a save on the live archive, audio playback, Safari.

## Clickable Progress bars

`app_1bfdd70/` went live the same day. Clicking part of a Progress bar now shows exactly the clips that part counts, and Clear or a second click puts the range and status back.

- `oncvm`'s Python 3.10: 411 passed, 4 skipped. Local JavaScript: 127 passed.
- Live read-only check through the VPN proxy, with no reviewer profile: 2026-10-05, 2026-03-02 and All Dates. Each picked part showed the count on its tooltip (1, 113, 115, 42, 16,818), paging stayed inside it, and a clip opened as "10 / 113" on page 2. Clear and a second click restored the range and status. Changing the date let go of the part. No console errors or server tracebacks.
- A picked part took 1.5 to 7 seconds to appear, including the 16,818-clip part on All Dates (5.6 seconds).
- The exception is the first All Dates load after a restart, while the page says "Updating...". Three bar clicks then took 15, 78 and 138 seconds and a slider change took 27, because a click also waits for that load to finish. During the 78-second wait the server used no CPU and three small requests ended at the same moment, so the time was not spent filtering. The cause of the long waits is not proven. They may be the VPN tunnel stalls seen behind the queue hang.
- All 94 review files still match the hashes from before the first start, and no JSON file in the archive is newer than the restart.
- Saving from a picked part was checked on copied data only.

## Faster clip opening

`app_2ebf6fa/` went live the same day. Over the VPN the link carries about 1 MB per second, and one clip open pulled about 75 MB while its picture is 1 to 5 MB. The server answered in about 0.2 seconds, so the delay was all traffic. A clip now loads its picture first, then its raw data for the contrast slider, then its audio and the neighbouring clips, one image at a time.

| Through the VPN, 15 steps each | Before | After |
|---|---|---|
| Median, click or arrow to whole picture | 7.9 s | 4.2 s |
| Slowest | 64.5 s | 9.8 s |

- `oncvm`'s Python 3.10: 412 passed, 4 skipped. Local JavaScript: 137 passed.
- Live read-only check through the proxy: 16 of 16 on contrast drags, zoom, arrows, Play and reopening a clip. A first contrast drag previewed in 0.6 seconds. Bars, 2026-10-05, 2026-03-02 and All Dates showed the same counts as before. No console errors or server tracebacks.
- A clip's audio now loads later, up to about 15 seconds after opening on a busy link. Play loads it straight away.
- All 94 review files still match the hashes from before the first start, and no JSON file in the archive is newer than this restart.
- Not checked: a save on the live archive, and the page-length menu, which has zero height on these clips in this build and the one before.

For about eight minutes after this restart the link stalled for 60 to 130 seconds at a time, and one arrow took 195 seconds. The server was idle, and the VPN client printed `lwip_data_cb: could not allocate pbuf` many times, so `ocproxy` was running out of packet buffers and dropping data. Waits of 64 and 85 seconds on the build before look the same. The dashboard cannot prevent these, and the Cisco client should not have them, but neither has been tested.

## Rollback

Copies of all 94 review files from before this build could write to them are in `backups/predictions-before-20261105T060856Z.tar.gz`, with a second copy in `oncvm_ONC/verification_backups/anomaly-review-20261105T060856Z/` on WhaleStor. No review had been saved when `app_2ebf6fa/` went live, so these are still current as of that restart.

`app_1bfdd70/` is the previous build, then `app_3d2f1f2_queue_fix/`, and `app_3d2f1f2/` is the one before the fix. To go back, start the folder you want with the same command and change its name in `oncvm_restart_after_reboot.sh`.

To stop the dashboard, run `screen -S anomaly-review -X quit`. If `oncvm-daq` comes back, use only one of the two dashboards, because both write to the same review files.
